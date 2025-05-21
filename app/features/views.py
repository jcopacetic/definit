import base64
import hashlib
import hmac
import json
import logging
import time
from functools import wraps
from typing import Dict, Any, Union, Tuple, Optional

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from app.dashboard.models import Customer
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
    Validate that the request is actually coming from HubSpot by checking
    the signature against the customer's HubSpot app key.
    
    Args:
        request: The HTTP request
        customer: The customer object with the HubSpot secret app key
    
    Raises:
        WebhookValidationError: If the validation fails
    """
    # Check for required headers
    signature_header = request.headers.get("X-HubSpot-Signature-v3")
    if not signature_header:
        raise WebhookValidationError("Missing HubSpot signature header")

    timestamp = request.headers.get("X-HubSpot-Request-Timestamp")
    if not timestamp:
        raise WebhookValidationError("Missing HubSpot timestamp header")

    # Validate timestamp
    try:
        current_time = int(time.time() * 1000)
        request_time = int(timestamp)
    except ValueError:
        raise WebhookValidationError("Invalid timestamp format", 400)

    # Check if the request is too old
    max_allowed_age = 300_000  # 5 minutes in milliseconds
    if current_time - request_time > max_allowed_age:
        raise WebhookValidationError("Request expired - timestamp too old")

    # Get the secret from the customer
    secret = customer.hubspot_secret_app_key
    if not secret:
        logger.critical(f"Customer {customer.id} has no HubSpot secret app key")
        raise WebhookValidationError("HubSpot secret not configured for customer", 500)

    # Build the signature base string
    method = request.method.upper()
    hostname = request.get_host()
    uri = request.build_absolute_uri()
    
    # Parse the body
    try:
        body = request.body.decode("utf-8") if request.body else ""
        if body and request.content_type == "application/json":
            # Normalize JSON spacing
            body = json.dumps(json.loads(body))
    except UnicodeDecodeError:
        logger.exception("Failed to decode request body")
        raise WebhookValidationError("Invalid request body encoding", 400)
    except json.JSONDecodeError:
        logger.exception("Invalid JSON in request body")
        raise WebhookValidationError("Invalid JSON in request body", 400)

    # Calculate expected signature
    signature_base = f"{method}{uri}{body}{timestamp}"
    try:
        calculated = hmac.new(
            key=secret.encode("utf-8"),
            msg=signature_base.encode("utf-8"),
            digestmod=hashlib.sha256
        ).digest()
        calculated_b64 = base64.b64encode(calculated).decode("utf-8")
    except Exception as e:
        logger.exception(f"Error calculating signature: {str(e)}")
        raise WebhookValidationError("Error calculating signature", 500)

    # Compare signatures
    if not hmac.compare_digest(calculated_b64, signature_header):
        raise WebhookValidationError("Invalid HubSpot signature")


def parse_webhook_payload(request) -> Dict[str, Any]:
    """
    Parse and validate the webhook payload.
    
    Returns:
        Dict containing the parsed payload
        
    Raises:
        ValueError: If parsing fails
    """
    try:
        payload = json.loads(request.body.decode('utf-8'))
        if not isinstance(payload, dict):
            raise ValueError("Payload must be a JSON object")
        return payload
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
        deal = hs_client.get_deal(deal_id)
        if not deal:
            logger.error(f"Could not fetch deal {deal_id} from HubSpot")
            return False, f"Could not fetch deal {deal_id}"
        
        logger.info(f"Successfully fetched deal {deal_id} data: {json.dumps(deal)[:200]}...")
        
        # TODO: Logic for looking up Excel row by deal ID
        # TODO: Logic for updating deal row in Excel/MS Graph
        
        # Initialize MS Graph client if needed
        # ms_graph_client = MSGraphClient(customer.msgraph_access_token)
        # response = ms_graph_client.update_excel_row(...)
        
        return True, "Deal stage change processed successfully"
        
    except Exception as e:
        logger.exception(f"Error processing deal stage change for deal {deal_id}: {str(e)}")
        return False, f"Error processing deal: {str(e)}"


@csrf_exempt
@require_POST
def hubspot_to_msgraph_webhook_listener(request):
    """
    Webhook listener for HubSpot events, particularly deal stage changes.
    Processes the webhook payload and updates Excel via MS Graph when appropriate.
    
    Returns:
        HttpResponse: Appropriate response based on processing result
    """
    request_id = f"req_{int(time.time() * 1000)}"
    logger.info(f"[{request_id}] Received HubSpot webhook request")
    try:
        logger.info(f"Request vars: {vars(request)}")
    except TypeError:
        logger.info(f"Request dir: {dir(request)}")
    
    try:
        # Extract query parameters
        portal_id = request.GET.get("portalId")
        object_id = request.GET.get("objectId")
        
        if not portal_id:
            logger.warning(f"[{request_id}] Missing portalId in request")
            return JsonResponse({"error": "Missing portalId parameter"}, status=400)
            
        if not object_id:
            logger.warning(f"[{request_id}] Missing objectId in request")
            return JsonResponse({"error": "Missing objectId parameter"}, status=400)
        
        # Get customer from portal ID
        try:
            customer = get_customer_from_portal_id(portal_id)
            logger.info(f"[{request_id}] Found customer: {customer.id} for portal: {portal_id}")
        except Exception as e:
            logger.error(f"[{request_id}] Failed to get customer: {str(e)}")
            return JsonResponse({"error": f"Customer lookup failed: {str(e)}"}, status=400)
        
        # Validate HubSpot signature
        try:
            validate_hubspot_signature(request, customer)
            logger.debug(f"[{request_id}] HubSpot signature validation successful")
        except WebhookValidationError as e:
            logger.warning(f"[{request_id}] Webhook validation failed: {e.message}")
            return HttpResponseForbidden(e.message)
        
        # Parse the webhook payload
        try:
            payload = parse_webhook_payload(request)
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
        
        # Log the received event
        event_id = payload.get('eventId', 'unknown')
        event_type = payload.get('subscriptionType', 'unknown')
        logger.info(f"[{request_id}] Processing HubSpot event: {event_id}, type: {event_type}")
        
        # Handle different event types
        if event_type == 'deal.propertyChange':
            # Process deal stage change
            success, message = process_deal_stage_change(customer, object_id, payload)
            
            if success:
                logger.info(f"[{request_id}] Successfully processed deal stage change: {message}")
                return JsonResponse({"status": "success", "message": message})
            else:
                logger.error(f"[{request_id}] Failed to process deal stage change: {message}")
                return JsonResponse({"status": "error", "message": message}, status=500)
                
        else:
            # Unrecognized event type - acknowledge receipt but take no action
            logger.info(f"[{request_id}] Unhandled HubSpot event type: {event_type}")
            return HttpResponse("Acknowledged unhandled event type", status=202)
            
    except Exception as e:
        logger.exception(f"[{request_id}] Unhandled exception in webhook processing: {str(e)}")
        return JsonResponse(
            {"error": "Internal server error", "message": str(e)},
            status=500
        )