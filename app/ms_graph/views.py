import logging
import time

from datetime import datetime, timezone
from dateutil import parser

from django.conf import settings
from django.shortcuts import render
from django.http import HttpResponse, Http404
from django.core.exceptions import ObjectDoesNotExist
from django.template import Template, Context
from itsdangerous import TimestampSigner, BadSignature, SignatureExpired

from app.dashboard.models import Customer 
from app.ms_graph.client import MSGraphClient 
from app.hubspot.client import HubSpotClient

logger = logging.getLogger(__name__)


def excel_note_to_hubspot(request, signed_row):
    """
    Process Excel note submission to HubSpot.
    Args:
        request: Django HTTP request object
        signed_row: Signed row number string
    Returns:
        HttpResponse: HTML response with auto-close script
    """

    customer, feature = _get_customer_and_feature()
    if not customer or not feature:
        return _render_error_response("Customer or feature configuration not found")
    logger.info(f"Using customer: {customer.id}, feature: {feature.id}")

    try:
        ms_client = MSGraphClient(customer)
    except Exception as e:
        logger.error(f"Failed to initialize MS Graph client: {str(e)}")
        return _render_error_response("Failed to connect to Microsoft Graph")
    try:
        # # Verify the signature and extract the row number
        # excel_row = ms_client._verify_signed_row(signed_row, settings.SECRET_KEY)
        
        # if excel_row is None:
        #     logger.error(f"Invalid or expired signature: {signed_row}")
        #     return _render_error_response("Invalid or expired link")

        # if excel_row < 1:
        #     logger.error(f"Excel row must be positive: {excel_row}")
        #     return _render_error_response("Row number must be positive")

        # logger.info(f"Processing Excel note to HubSpot for verified row {excel_row}")

        
        current_time_stamp = datetime.now(timezone.utc)

        excel_row = signed_row

        time.sleep(30)

        workbook_last_save_stamp = ms_client.get_worksheet_last_saved_timestamp(
            workbook_item_id=feature.workbook_id, 
            worksheet_name=feature.worksheet_name,
        )

        if isinstance(workbook_last_save_stamp, str):
            workbook_last_save_stamp = parser.isoparse(workbook_last_save_stamp)
        logger.debug(f"Workbook last saved timestamp: {workbook_last_save_stamp.isoformat()}")

        # Parse submission time and make timezone-aware (assumed to be UTC)
        submission_time = current_time_stamp
        if submission_time.tzinfo is None:
            submission_time = submission_time.replace(tzinfo=timezone.utc)
        logger.debug(f"Submission timestamp: {submission_time.isoformat()}")

        note_value = _get_excel_cell_value(ms_client, feature, excel_row, "Submit a Note")
        if not note_value:
            logger.info(f"No note value found in row {excel_row}")
            return _render_success_response("No note to submit")

        logger.info(f"Retrieved note value from Excel (length: {len(note_value)})")

        deal_id = _get_excel_cell_value(ms_client, feature, excel_row, "Record ID")
        deal_name = _get_excel_cell_value(ms_client, feature, excel_row, "Deal Name")
        if not deal_id:
            logger.warning(f"No deal ID found in row {excel_row}")
            return _render_error_response("Deal ID not found in Excel row")

        logger.info(f"Processing deal ID: {deal_id}")

        success = _create_hubspot_note(customer, deal_id, note_value)
        if not success:
            return _render_error_response("Failed to create note in HubSpot")

        _clear_excel_cell(ms_client, feature, excel_row)

        deal_info = {
            "row_id": excel_row,
            "deal_name": deal_name,
            "deal_id": deal_id,
            "note": note_value,
            "last_saved": workbook_last_save_stamp.strftime("%Y-%m-%d %H:%M:%S.") + f"{int(workbook_last_save_stamp.microsecond / 1000):03d}",
            "submitted": current_time_stamp.strftime("%Y-%m-%d %H:%M:%S.") + f"{int(current_time_stamp.microsecond / 1000):03d}",
        }

        logger.info(f"Successfully processed note for deal {deal_id}")
        return _render_success_response(deal_info, "Note submitted successfully")

    except Exception as e:
        logger.error(f"Unexpected error in excel_note_to_hubspot: {str(e)}", exc_info=True)
        return _render_error_response("An unexpected error occurred")
    

def _get_signer():
    """Return a TimestampSigner with project-level secret."""
    secret = getattr(settings, "EXCEL_SIGNATURE_SECRET", settings.SECRET_KEY)
    return TimestampSigner(secret)


def _get_customer_and_feature():
    try:
        customer = Customer.objects.first()
        if not customer:
            logger.error("No customer found in database")
            return None, None

        feature = customer.features.first()
        if not feature:
            logger.error(f"No features found for customer {customer.id}")
            return None, None

        if not all([feature.workbook_id, feature.worksheet_id]):
            logger.error(f"Feature {feature.id} missing required workbook/worksheet IDs")
            return None, None

        return customer, feature

    except ObjectDoesNotExist as e:
        logger.error(f"Database error retrieving customer/feature: {str(e)}")
        return None, None
    except Exception as e:
        logger.error(f"Unexpected error retrieving customer/feature: {str(e)}")
        return None, None


def _get_excel_cell_value(ms_client, feature, row_number, header_name):
    try:
        value = ms_client.get_cell_value_by_header(
            workbook_item_id=feature.workbook_id,
            worksheet_id=feature.worksheet_id,
            row_number=row_number,
            header_name=header_name,
        )
        if value:
            return str(value).strip() or None
        return None

    except Exception as e:
        logger.error(
            f"Error retrieving Excel cell value (row: {row_number}, "
            f"header: {header_name}): {str(e)}"
        )
        return None


def _create_hubspot_note(customer, deal_id, note_value):
    try:
        if not customer.hubspot_secret_app_key:
            logger.error(f"Customer {customer.id} missing HubSpot API key")
            return False

        hs_client = HubSpotClient(customer.hubspot_secret_app_key)
        created_note = hs_client.create_note_on_deal(deal_id, note_value)

        if created_note:
            logger.info(f"Successfully created HubSpot note for deal {deal_id}")
            return True
        else:
            logger.error(f"Failed to create HubSpot note for deal {deal_id}")
            return False

    except Exception as e:
        logger.error(f"Error creating HubSpot note for deal {deal_id}: {str(e)}")
        return False


def _clear_excel_cell(ms_client, feature, excel_row):
    try:
        cell_address = f"J{excel_row}"
        cell_update = ms_client.update_cell(
            feature.workbook_id,
            feature.worksheet_id,
            cell_address,
            "",
        )
        if cell_update:
            logger.info(f"Successfully cleared Excel cell {cell_address}")
        else:
            logger.warning(f"Failed to clear Excel cell {cell_address}")

    except Exception as e:
        logger.error(f"Error clearing Excel cell J{excel_row}: {str(e)}")


def _render_success_response(deal_info, message="Operation completed successfully"):
    """
    Render success response with auto-close script.
    
    Args:
        message: Success message to display
        
    Returns:
        HttpResponse: HTML response
    """
    template_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Success</title>
            <meta charset="utf-8">
        </head>
        <body>
            <div style="font-family: Arial, sans-serif; text-align: center; padding: 20px;">
            <h2 style="color: green;">✓ Success</h2>
            <p>{{ message }}</p>
            <br>
            <p><strong>Row ID</strong> {{ deal_info.row_id|default:"" }}<br>
            <strong>Deal ID</strong> {{ deal_info.deal_id|default:"" }}<br>
            <strong>Deal Name</strong> {{ deal_info.deal_name|default:"" }}<br>
            <strong>Note</strong> {{ deal_info.note|default:"" }}<br>
            <strong>Workbook Last Saved Timestamp</strong> {{deal_info.last_saved}}<br>
            <strong>Submission happened at</strong> {{deal_info.submitted}}</p>
            <br>
            <p><small>This window will close automatically...</small></p>
            </div>
            
        </body>
        </html>
        """
    
    
    template = Template(template_content)
    context = Context({'deal_info': deal_info or {}, 'message': message})
    return HttpResponse(template.render(context))


def _render_error_response(error_message="An error occurred"):
    """
    Render error response with auto-close script.
    
    Args:
        error_message: Error message to display
        
    Returns:
        HttpResponse: HTML response
    """
    template_content = """
    <!DOCTYPE html>
    <html>
      <head>
        <title>Error</title>
        <meta charset="utf-8">
      </head>
      <body>
        <div style="font-family: Arial, sans-serif; text-align: center; padding: 20px;">
          <h2 style="color: red;">✗ Error</h2>
          <p>{{ error_message }}</p>
          <p><small>This window will close automatically...</small></p>
        </div>
        <script>
          setTimeout(() => {
            try {
              window.close();
            } catch (e) {
              // Fallback if window.close() is blocked
              document.body.innerHTML = '<div style="text-align: center; padding: 20px;"><h3>Please close this window</h3></div>';
            }
          }, 3000);
        </script>
      </body>
    </html>
    """
    
    template = Template(template_content)
    context = Context({'error_message': error_message})
    return HttpResponse(template.render(context))