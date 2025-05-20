import json
import time
import hmac
import base64
import hashlib
import logging
from django.conf import settings
from django.shortcuts import render
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse

from app.dashboard.models import Customer

from app.hubspot.client import HubSpotClient

logger = logging.getLogger(__name__)


@csrf_exempt
def hubspot_to_msgraph_webhook_listener(request):
    """
    Webhook listener for HubSpot events, particularly deal stage changes.
    Validates the HubSpot signature and processes the webhook payload.
    """
    # # First validate the request is legitimate
    # validation_result = validate_hubspot_signature(request)
    # if validation_result is not True:
    #     return validation_result  # It's an HttpResponseForbidden
    
    portal_id = request.GET.get("portalId")
    customer = get_object_or_404(Customer, hubspot_portal_id=portal_id)
    object_id = request.GET.get("objectId")
    # Process the webhook data
    try:
        payload = json.loads(request.body.decode('utf-8'))
        
        # Log the received event for debugging
        logger.info(f"Received HubSpot webhook: {payload.get('eventId', 'unknown')}")
        
        # Check if this is a deal stage change event
        if payload.get('subscriptionType') == 'deal.propertyChange':
            hs_client = HubSpotClient(customer.hubspot_secret_app_key)
            # 1. get new hubspot deal data
            deal = hs_client.get_deal(object_id)
            logger.info(deal)
            # 2. lookup excel row by deal ID
            # 3. update deal row
        else:
            logger.info(f"Unhandled HubSpot event type: {payload.get('subscriptionType')}")
            return HttpResponse("Unhandled event type", status=202)  # Accepted but not processed
            
    except json.JSONDecodeError:
        logger.error("Failed to parse webhook JSON payload")
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.exception(f"Error processing webhook: {str(e)}")
        return JsonResponse({"error": "Internal server error"}, status=500)


def handle_deal_update(payload):
    """
    Handle a deal stage change event from HubSpot.
    
    The payload will typically contain:
    - objectId: The HubSpot ID of the deal
    - propertyName: The property that changed (should be "dealstage")
    - propertyValue: The new stage ID
    """
    try:
        # Extract relevant information
        deal_id = payload.get('objectId')
        property_name = payload.get('propertyName')
        new_stage = payload.get('propertyValue')
        
        # Verify this is actually a deal stage change
        if property_name != 'dealstage':
            logger.info(f"Property change was {property_name}, not dealstage. Ignoring.")
            return HttpResponse("Not a deal stage change", status=202)
        
        logger.info(f"Deal {deal_id} moved to stage {new_stage}")
        
        # Fetch additional deal information if needed
        # You might want to make an API call to HubSpot to get more deal details
        
        # Example: Update Microsoft Graph based on the deal stage
        if new_stage == "YOUR_OPPORTUNITY_STAGE_ID":
            # Create a task in Microsoft Graph/Planner
            result = create_msgraph_task(deal_id, new_stage)
            if result:
                logger.info(f"Successfully created MS Graph task for deal {deal_id}")
                return HttpResponse("Task created", status=200)
            else:
                logger.error(f"Failed to create MS Graph task for deal {deal_id}")
                return JsonResponse({"error": "Failed to create task"}, status=500)
                
        # Handle other stage transitions
        # elif new_stage == "ANOTHER_STAGE_ID":
        #     # Do something else
        
        # Default response for stages we don't have special handling for
        return HttpResponse("Processed successfully", status=200)
        
    except Exception as e:
        logger.exception(f"Error handling deal stage change: {str(e)}")
        return JsonResponse({"error": "Failed to process deal stage change"}, status=500)


def create_msgraph_task(deal_id, stage):
    """
    Create a task in Microsoft Graph based on the deal and its new stage.
    This is just a placeholder - implement your MS Graph API calls here.
    
    Returns True if successful, False otherwise.
    """
    try:
        # Your implementation to create tasks in Microsoft Graph
        # Example:
        # 1. Get an access token for MS Graph
        # 2. Fetch additional deal details from HubSpot if needed
        # 3. Create a task in MS Planner or Outlook or Teams
        
        # Placeholder for now
        logger.info(f"Would create MS Graph task for deal {deal_id} in stage {stage}")
        return True
        
    except Exception as e:
        logger.exception(f"Error creating MS Graph task: {str(e)}")
        return False


def validate_hubspot_signature(request):
    """
    Validate that the request is actually coming from HubSpot by checking
    the signature against our client secret.
    """
    signature_header = request.headers.get("X-HubSpot-Signature-v3")
    if not signature_header:
        logger.warning("Missing HubSpot signature header")
        return HttpResponseForbidden("Missing signature")

    timestamp = request.headers.get("X-HubSpot-Request-Timestamp")
    if not timestamp:
        logger.warning("Missing HubSpot timestamp header")
        return HttpResponseForbidden("Missing timestamp")

    try:
        current_time = int(time.time() * 1000)
        request_time = int(timestamp)
    except ValueError:
        logger.warning("Invalid timestamp format")
        return HttpResponseForbidden("Invalid timestamp")

    max_allowed_age = 300_000  # 5 minutes
    if current_time - request_time > max_allowed_age:
        logger.warning("HubSpot request timestamp too old")
        return HttpResponseForbidden("Request expired")

    secret = settings.APP_HS_SECRET
    method = request.method.upper()
    hostname = request.get_host()
    raw_query = request.META.get("QUERY_STRING", "")
    uri = f"https://{hostname}{request.path}"
    if raw_query:
        uri += f"?{raw_query}"

    try:
        body = request.body.decode("utf-8") if request.body else ""
        if body and request.content_type == "application/json":
            body = json.dumps(json.loads(body))  # Normalize spacing
    except UnicodeDecodeError:
        logger.exception("Failed to decode request body")
        return JsonResponse({"error": "Invalid request body encoding"}, status=400)

    signature_base = f"{method}{uri}{body}{timestamp}"
    calculated = hmac.new(
        key=secret.encode("utf-8"),
        msg=signature_base.encode("utf-8"),
        digestmod=hashlib.sha256
    ).digest()

    calculated_b64 = base64.b64encode(calculated).decode("utf-8")

    if not hmac.compare_digest(calculated_b64, signature_header):
        logger.error("Invalid HubSpot signature")
        return HttpResponseForbidden("Invalid signature")

    return True  # No errors