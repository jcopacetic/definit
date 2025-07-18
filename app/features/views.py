import base64
import hashlib
import hmac
import json
import logging
import time
import requests
from functools import wraps
from typing import Dict, Any, Union, Tuple, Optional, List

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse, HttpRequest
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from app.dashboard.models import Customer
from app.features.models import CustomerFeature

from app.hubspot.client import HubSpotClient
from app.ms_graph.client import MSGraphClient

# Configure logger
logger = logging.getLogger(__name__)


class WebhookValidationError(Exception):
    """Custom exception for webhook validation failures."""
    def __init__(self, message: str, status_code: int = 403):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


def hubspot_signature_required(f):
    """
    Decorator to validate HubSpot webhook signatures before processing.
    This needs to be applied AFTER we retrieve the customer.
    """
    @wraps(f)
    def decorated_function(request, customer, *args, **kwargs):
        try:
            validate_hubspot_signature(request, customer)
            return f(request, customer, *args, **kwargs)
        except WebhookValidationError as e:
            logger.warning(f"Webhook validation failed: {e.message}")
            return HttpResponseForbidden(e.message)
        except Exception as e:
            logger.exception(f"Unexpected error in signature validation: {str(e)}")
            return JsonResponse({"error": "Internal server error"}, status=500)
    
    return decorated_function


def validate_hubspot_signature(request, customer: Customer) -> None:
    """
    Validates a HubSpot webhook request using the v3 signature scheme.
    """
    signature_header = request.headers.get("X-HubSpot-Signature-v3")
    if not signature_header:
        logger.warning("Missing HubSpot signature header")
        raise WebhookValidationError("Missing HubSpot signature header")

    timestamp = request.headers.get("X-HubSpot-Request-Timestamp")
    if not timestamp:
        logger.warning("Missing HubSpot timestamp header")
        raise WebhookValidationError("Missing HubSpot timestamp header")

    # Validate timestamp format and age
    try:
        current_time = int(time.time() * 1000)
        request_time = int(timestamp)
    except ValueError:
        logger.warning("Invalid HubSpot timestamp format")
        raise WebhookValidationError("Invalid timestamp format", 400)

    max_age_ms = 300_000  # 5 minutes
    if current_time - request_time > max_age_ms:
        logger.warning(f"Request expired. Current time: {current_time}, request time: {request_time}")
        raise WebhookValidationError("Request expired - timestamp too old")

    # Get the secret
    secret = customer.hubspot_client_secret
    if not secret:
        logger.critical(f"Customer {customer.id} missing HubSpot secret key")
        raise WebhookValidationError("HubSpot secret not configured for customer", 500)

    try:
        # Build the source string exactly as HubSpot does
        method = request.method.upper()
        
        # Important: Use the exact host and path as received
        host = request.get_host()
        path = request.get_full_path()  # This includes query parameters
        uri = f"https://{host}{path}"
        
        # Get raw body - this is critical
        body = getattr(request, '_body', None) or request.body
        if hasattr(request, '_body'):
            # If body was already read, use the cached version
            body = request._body
        else:
            # Read and cache the body for potential future use
            body = request.body
            request._body = body
        
        # Build signature source string in exact order
        source_string = (
            method.encode('utf-8') +
            uri.encode('utf-8') +
            body +
            timestamp.encode('utf-8')
        )
        
        logger.debug(f"Signature source string components:")
        logger.debug(f"  Method: {method}")
        logger.debug(f"  URI: {uri}")
        logger.debug(f"  Body length: {len(body)}")
        logger.debug(f"  Timestamp: {timestamp}")
        
        # Calculate signature
        calculated_signature = hmac.new(
            key=secret.encode('utf-8'),
            msg=source_string,
            digestmod=hashlib.sha256
        ).digest()
        
        calculated_b64 = base64.b64encode(calculated_signature).decode('utf-8')
        
        logger.debug(f"Expected signature: {signature_header}")
        logger.debug(f"Calculated signature: {calculated_b64}")
        
    except Exception as e:
        logger.exception("Error during signature calculation")
        raise WebhookValidationError("Error calculating signature", 500)

    # Compare signatures using constant-time comparison
    if not hmac.compare_digest(calculated_b64, signature_header):
        logger.warning("Signature mismatch during HubSpot validation")
        logger.warning(f"Expected: {signature_header}")
        logger.warning(f"Calculated: {calculated_b64}")
        raise WebhookValidationError("Invalid HubSpot signature")

    logger.info("HubSpot signature validation successful")


# Alternative middleware approach to preserve request body
class PreserveRequestBodyMiddleware:
    """
    Middleware to preserve request body for signature validation
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Store the raw body before it's consumed
        if request.content_type == 'application/json':
            request._body = request.body
        
        response = self.get_response(request)
        return response



def parse_webhook_payload(request: HttpRequest) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Parse and validate the webhook payload.

    Returns:
        Parsed JSON payload (either a dict or list of dicts)
        
    Raises:
        ValueError: If parsing or validation fails
    """
    try:
        raw_body = request.body.decode('utf-8')
        logger.debug(f"Raw webhook payload: {raw_body}")
        payload = json.loads(raw_body)
        
        if isinstance(payload, dict):
            return payload
        elif isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
            return payload
        else:
            raise ValueError("Payload must be a JSON object or a list of JSON objects")
    
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse webhook JSON payload: {str(e)}")
        raise ValueError(f"Invalid JSON: {str(e)}")
    except UnicodeDecodeError as e:
        logger.error(f"Failed to decode webhook payload: {str(e)}")
        raise ValueError("Invalid payload encoding")


def get_customer_from_portal_id(portal_id: str) -> Customer:
    """
    Get a customer object from a HubSpot portal ID.
    
    Args:
        portal_id: The HubSpot portal ID
        
    Returns:
        Customer: The customer object
        
    Raises:
        Http404: If customer is not found
    """
    if not portal_id:
        logger.error("Missing portal ID in request")
        raise ValueError("Missing portal ID")
    
    logger.debug(f"Looking up customer for portal ID: {portal_id}")
    return get_object_or_404(Customer, hubspot_portal_id=portal_id)


def process_deal_stage_change(customer: Customer, deal_id: str, payload: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Process a deal stage change event.
    
    Args:
        customer: The customer object
        deal_id: The HubSpot deal ID
        payload: The webhook payload
        
    Returns:
        Tuple of (success, message)
    """
    try:
        # Initialize HubSpot client
        hs_client = HubSpotClient(customer.hubspot_secret_app_key)
        
        # Get updated deal data from HubSpot
        deal_parse = hs_client.collect_parse_deal_data(deal_id)

        if not deal_parse:
            logger.error(f"Could not fetch deal {deal_id} from HubSpot")
            return False, f"Could not fetch deal {deal_id}"
        
        logger.info(f"Successfully parsed  deal {deal_id} data: {json.dumps(deal_parse)[:200]}...")
        
        try:
            customerfeature = CustomerFeature.objects.get(customer=customer, feature__id=1)
        except CustomerFeature.DoesNotExist:
            logger.warning("customer feature doesn't exist")
            return HttpResponse(status=404)

        for deal_id, details in deal_parse.items():
            logger.info(f"Processing deal {deal_id}")

            ms_client = MSGraphClient(customer)

            is_existing_row = ms_client.find_row_by_id(
                customerfeature.workbook_id, 
                customerfeature.worksheet_id, 
                "Record ID",
                deal_id,
            )

            logger.info(f"is_existing_row: {is_existing_row}")

            if is_existing_row:
                row_to_update = is_existing_row
            else: 
                row_to_update = customerfeature.worksheet_last_row + 1


            data_to_add = {
                "deal_id": deal_id,
                "name": details.get('name', ''),
                "deal_link": details.get("deal_link", ""),
                "plans_link": details.get('plans_link', ""),
                "quote_link": details.get("quote_link", ""),
                "deal_stage": details.get("deal_stage", ""),
                "latest_bid_date": details.get("latest_bid_date", ""),
                "deal_amount": details.get("deal_amount", ""),
                "deal_owner": details.get("deal_owner", ""),
                "associated_contact": details.get("associated_contact", ""),
                "associated_company": details.get("associated_company", ""),
                "city": details.get("city", ""),
                "state": details.get("state", ""),
                "last_contacted": details.get("last_contacted", ""),
                "last_contacted_type": details.get("last_contacted_type"),
                "last_engagement": details.get("last_engagement"),
                "last_engagement_type": details.get("last_engagement_type"),
                "email": details.get("email", ""),
                "note": details.get("note", ""),
                "task": details.get("task", ""),
                "meeting": details.get("meeting", ""),
                "call": details.get("call", ""),
            }

            logger.info(f"deal: {deal_id}, row: {row_to_update}")

            parse_row = ms_client.parse_deal_to_excel_sheet(
                customerfeature.workbook_id, 
                customerfeature.worksheet_name, 
                data_to_add, 
                row_to_update,
            )

            logger.info(f"parse results: {parse_row}")

            if parse_row and not is_existing_row:
                customerfeature.worksheet_last_row += 1
                customerfeature.save()
        
        return True, "Deal stage change processed successfully"
        
    except Exception as e:
        logger.exception(f"Error processing deal stage change for deal {deal_id}: {str(e)}")
        return False, f"Error processing deal: {str(e)}"


def remove_deal_from_sheet(customer, object_id):
    """
    Remove a deal from the Excel sheet by deleting the corresponding row.
    
    Args:
        customer: Customer object
        object_id: The deal ID to remove from the sheet
        
    Returns:
        HttpResponse: HTTP response indicating success or failure
    """
    logger.info(f"Attempting to remove deal '{object_id}' from sheet for customer '{customer}'")
    
    try:
        # Initialize MS Graph client
        ms_client = MSGraphClient(customer)
        logger.debug(f"MS Graph client initialized for customer '{customer}'")
        
    except Exception as e:
        logger.error(f"Failed to initialize MS Graph client for customer '{customer}': {str(e)}")
        return HttpResponse("Failed to initialize Microsoft Graph client", status=500)

    try:
        # Get customer feature configuration
        customerfeature = CustomerFeature.objects.get(customer=customer, feature__id=1)
        logger.debug(f"Retrieved customer feature - workbook_id: {customerfeature.workbook_id}, worksheet: {customerfeature.worksheet_name}")
        
    except CustomerFeature.DoesNotExist:
        logger.warning(f"Customer feature doesn't exist for customer '{customer}' and feature id 1")
        return HttpResponse("Customer feature configuration not found", status=404)
    except Exception as e:
        logger.error(f"Unexpected error retrieving customer feature for customer '{customer}': {str(e)}")
        return HttpResponse("Error retrieving customer configuration", status=500)

    # Validate required configuration
    if not customerfeature.workbook_id or not customerfeature.worksheet_name:
        logger.error(f"Missing required configuration - workbook_id: {customerfeature.workbook_id}, worksheet_name: {customerfeature.worksheet_name}")
        return HttpResponse("Incomplete Excel sheet configuration", status=400)

    try:
        # Attempt to remove the deal from the Excel sheet
        logger.info(f"Removing deal '{object_id}' from workbook '{customerfeature.workbook_id}', worksheet '{customerfeature.worksheet_name}'")
        
        remove_row_from_sheet = ms_client.delete_deal_from_excel_sheet(
            customerfeature.workbook_id, 
            customerfeature.worksheet_name,
            object_id,
        )
        
        if remove_row_from_sheet:
            customerfeature.worksheet_last_row -= 1
            customerfeature.save()
            logger.info(f"Successfully removed deal '{object_id}' from Excel sheet for customer '{customer}'")
            return HttpResponse("Deal removed from sheet successfully", status=200)
        else:
            logger.warning(f"Failed to remove deal '{object_id}' from Excel sheet - deal may not exist or API call failed")
            return HttpResponse("Deal not found in sheet or removal failed", status=404)
            
    except Exception as e:
        logger.error(f"Unexpected error removing deal '{object_id}' from Excel sheet for customer '{customer}': {str(e)}")
        return HttpResponse("Error removing deal from sheet", status=500)
    
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP Error removing deal '{object_id}': {e.response.status_code} - {e.response.text}")
        return HttpResponse(f"Microsoft Graph API error: {e.response.status_code}", status=502)
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error removing deal '{object_id}': {str(e)}")
        return HttpResponse("Network error communicating with Microsoft Graph", status=503)


@csrf_exempt
@require_POST
def hubspot_to_msgraph_webhook_listener(request):
    """
    Webhook listener for HubSpot events with improved body handling.
    """
    request_id = f"req_{int(time.time() * 1000)}"
    logger.info(f"[{request_id}] Received HubSpot webhook request")

    # 1. Preserve the raw body for signature validation
    if not hasattr(request, '_body'):
        request._body = request.body

    # 2. Parse JSON body (using cached body if available)
    try:
        body_bytes = getattr(request, '_body', request.body)
        body_str = body_bytes.decode('utf-8')
        body = json.loads(body_str)
        logger.info(f"[{request_id}] Request body parsed successfully")
    except Exception as e:
        logger.warning(f"[{request_id}] Failed to parse request body: {e}")
        return JsonResponse({"error": "Invalid JSON payload"}, status=400)

    # Extract portalId and objectId
    try:
        if isinstance(body, list) and body:
            data = body[0]
        elif isinstance(body, dict):
            data = body
        else:
            raise ValueError("Unexpected payload format")

        portal_id = data.get("portalId") or data.get("portal_id")
        object_id = data.get("objectId")

        if not portal_id:
            return JsonResponse({"error": "Missing portalId"}, status=400)
        if not object_id:
            return JsonResponse({"error": "Missing objectId"}, status=400)

    except Exception as e:
        logger.error(f"[{request_id}] Failed to extract required fields: {e}")
        return JsonResponse({"error": "Malformed request body"}, status=400)

    # 3. Customer lookup
    try:
        customer = get_customer_from_portal_id(portal_id)
        logger.info(f"[{request_id}] Found customer {customer.id}")
    except Exception as e:
        logger.error(f"[{request_id}] Customer lookup failed: {e}")
        return JsonResponse({"error": f"Customer lookup failed: {str(e)}"}, status=400)

    # 4. Validate signature AFTER we have customer but BEFORE processing
    try:
        validate_hubspot_signature(request, customer)
        logger.debug(f"[{request_id}] Signature validation successful")
    except WebhookValidationError as e:
        logger.warning(f"[{request_id}] Signature validation failed: {e.message}")
        return HttpResponseForbidden(e.message)

    # --- Step 5: Parse payload ---
    request_id = f"req_{int(time.time() * 1000)}"  # Example request ID, adjust as needed
    try:
        payload = parse_webhook_payload(request)

        if isinstance(payload, list):
            for event in payload:
                event_id = event.get("eventId", "unknown")
                event_type = event.get("subscriptionType", "unknown")
                event_object_type_id = event.get("objectTypeId", "unknown")
                event_object_id = event.get("objectId", "unknown")
                logger.info(f"[{request_id}] Processing HubSpot event {event_id} of type {event_type}")
        else:
            event_id = payload.get("eventId", "unknown")
            event_type = payload.get("subscriptionType", "unknown")
            logger.info(f"[{request_id}] Processing HubSpot event {event_id} of type {event_type}")

        # return JsonResponse({"status": "success"})

    except ValueError as e:
        logger.error(f"[{request_id}] Payload parsing failed: {e}")
        return JsonResponse({"error": str(e)}, status=400)

    # --- Step 6: Handle specific event types ---

    print(f"\n\n\n{event_type} - {event_id} - {event_object_type_id} - {event_object_id}\n\n\n")

    if event_type == "object.creation":
        hs_client = HubSpotClient(customer.hubspot_secret_app_key)

        # Mapping of object type to association ID
        object_assoc_map = {
            "0-46": "214",  # Notes
            "0-27": "216",  # Tasks
            "0-48": "206",  # Calls
            "0-49": "210",  # Emails
            "0-53": "175",  # Invoices
            "0-14": "64",   # Quotes
            "0-47": "212",  # Meetings
            "0-18": "85",   # Communications (sms, linkedin, whatsapp)
        }

        assoc_id = object_assoc_map.get(event_object_type_id)

        if not assoc_id:
            logger.warning(f"[{request_id}] Unknown event_object_type_id: {event_object_type_id}")
            return JsonResponse(
                {"status": "ignored", "message": "Unrecognized object type"},
                status=400
            )

        try:
            associated_deal_ids = hs_client.get_associations(
                event_object_type_id,
                event_object_id,
                "0-3",
                assoc_id,
            )
        except Exception as e:
            logger.exception(f"[{request_id}] Error fetching associations: {e}")
            return JsonResponse({"error": "HubSpot fetch failure", "message": str(e)}, status=500)

        if not associated_deal_ids:
            logger.info(f"[{request_id}] No associated deals found for object ID {event_object_id}")
            return JsonResponse({"status": "noop", "message": "No associated deals found"})

        for deal_id in associated_deal_ids:
            try:
                success, message = process_deal_stage_change(customer, deal_id, payload)
                if success:
                    logger.info(f"[{request_id}] Deal stage processed successfully: {message}")
                    return JsonResponse({"status": "success", "message": message})
                else:
                    logger.error(f"[{request_id}] Deal stage processing failed: {message}")
                    return JsonResponse({"status": "error", "message": message}, status=500)
            except Exception as e:
                logger.exception(f"[{request_id}] Error during deal stage processing: {e}")
                return JsonResponse({"error": "Processing failure", "message": str(e)}, status=500)

    if event_type in ["deal.propertyChange", "deal.creation", "deal.associationChange"]:
        try:
            success, message = process_deal_stage_change(customer, object_id, payload)
            if success:
                logger.info(f"[{request_id}] Deal stage processed successfully: {message}")
                return JsonResponse({"status": "success", "message": message})
            else:
                logger.error(f"[{request_id}] Deal stage processing failed: {message}")
                return JsonResponse({"status": "error", "message": message}, status=500)
        except Exception as e:
            logger.exception(f"[{request_id}] Error during deal stage processing: {e}")
            return JsonResponse({"error": "Processing failure", "message": str(e)}, status=500)
        
    if event_type == "deal.deletion":
        try:
            removed_deal = remove_deal_from_sheet(customer, object_id)
        except Exception as e:
            logger.exception(f"[{request_id}] Error during deal deletion: {e}")
            return JsonResponse({"error": "Processing failure", "message": str(e)}, status=500)

    else:
        logger.info(f"[{request_id}] Unhandled event type: {event_type}")
        return HttpResponse("Acknowledged unhandled event type", status=202)

    # --- Catch-All Fallback ---
    # (This may be unreachable but left for safety in future edits)
    return JsonResponse({"error": "Unexpected error"}, status=500)
