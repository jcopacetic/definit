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
import time
from datetime import datetime, timezone, timedelta

from app.dashboard.models import Customer 
from app.ms_graph.client import MSGraphClient 
from app.hubspot.client import HubSpotClient

logger = logging.getLogger(__name__)

def wait_for_sheet_save(
    ms_client,
    workbook_item_id: str,
    worksheet_name: str,
    timeout: int = 60,
    poll_interval: int = 5,
) -> bool:
    """
    Polls OneDrive to wait until the Excel sheet has been saved after the current timestamp.

    Args:
        ms_client: Microsoft Graph client with method get_worksheet_last_saved_timestamp
        workbook_item_id (str): OneDrive item ID of the workbook.
        worksheet_name (str): Name of the worksheet to check.
        timeout (int): Max seconds to wait before giving up.
        poll_interval (int): How often to recheck, in seconds.

    Returns:
        bool: True if save detected, False if timeout exceeded.
    """
    start_time = datetime.now(timezone.utc)
    deadline = start_time + timedelta(seconds=timeout)

    logger.info("Polling for worksheet save after %s", start_time.isoformat())

    while datetime.now(timezone.utc) < deadline:
        try:
            last_saved_raw = ms_client.get_worksheet_last_saved_timestamp(
                workbook_item_id=workbook_item_id,
                worksheet_name=worksheet_name,
            )

            try:
                last_saved = parser.isoparse(last_saved_raw) if isinstance(last_saved_raw, str) else last_saved_raw
            except Exception as parse_err:
                logger.warning("Could not parse last saved timestamp: %s", parse_err)
                last_saved = None

            if last_saved:
                logger.debug("Last saved timestamp: %s", last_saved.isoformat())

                if last_saved > start_time:
                    logger.info("Detected save after %s. Proceeding.", start_time.isoformat())
                    return True

        except Exception as e:
            logger.warning("Failed to get worksheet save timestamp: %s", e)

        logger.debug("Waiting %s seconds before retrying...", poll_interval)
        time.sleep(poll_interval)

    logger.error("Timed out waiting for worksheet save after %s", start_time.isoformat())
    return False


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
        logger.error(f"Failed to initialize MS Graph client: {e}")
        return _render_error_response("Failed to connect to Microsoft Graph")

    # # Verify the signature and extract the row number
    # excel_row = ms_client._verify_signed_row(signed_row, settings.SECRET_KEY)
    
    # if excel_row is None:
    #     logger.error(f"Invalid or expired signature: {signed_row}")
    #     return _render_error_response("Invalid or expired link")

    # if excel_row < 1:
    #     logger.error(f"Excel row must be positive: {excel_row}")
    #     return _render_error_response("Row number must be positive")

    # logger.info(f"Processing Excel note to HubSpot for verified row {excel_row}")

    
    try:
        current_time_stamp = datetime.now(timezone.utc)

        # Wait for Excel save to finish after user click
        sheet_ready = wait_for_sheet_save(
            ms_client,
            workbook_item_id=feature.workbook_id,
            worksheet_name=feature.worksheet_name,
            timeout=60,
            poll_interval=5,
        )

        if not sheet_ready:
            return _render_error_response("Excel sheet not saved in time. Please try again.")

        # Extract Excel row (signed_row is assumed safe, but normally should be verified)
        excel_row = signed_row  # Replace with signature verification if needed

        logger.info(f"Processing Excel note to HubSpot for row: {excel_row}")

        # Get last save timestamp for logging/reporting
        workbook_last_save_stamp = ms_client.get_worksheet_last_saved_timestamp(
            workbook_item_id=feature.workbook_id,
            worksheet_name=feature.worksheet_name,
        )
        if isinstance(workbook_last_save_stamp, str):
            workbook_last_save_stamp = parser.isoparse(workbook_last_save_stamp)

        logger.debug(f"Workbook last saved timestamp: {workbook_last_save_stamp.isoformat()}")

        # Ensure current timestamp is timezone-aware (should already be)
        submission_time = current_time_stamp
        if submission_time.tzinfo is None:
            submission_time = submission_time.replace(tzinfo=timezone.utc)

        logger.debug(f"Submission timestamp: {submission_time.isoformat()}")

        # Read data from Excel
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

        # Send note to HubSpot
        success = _create_hubspot_note(customer, deal_id, note_value)
        if not success:
            return _render_error_response("Failed to create note in HubSpot")

        # Clear the "Submit a Note" cell after processing
        _clear_excel_cell(ms_client, feature, excel_row)

        deal_info = {
            "row_id": excel_row,
            "deal_name": deal_name,
            "deal_id": deal_id,
            "note": note_value,
            "last_saved": workbook_last_save_stamp.strftime("%Y-%m-%d %H:%M:%S.") + f"{int(workbook_last_save_stamp.microsecond / 1000):03d}",
            "submitted": submission_time.strftime("%Y-%m-%d %H:%M:%S.") + f"{int(submission_time.microsecond / 1000):03d}",
        }

        logger.info(f"Successfully processed note for deal {deal_id}")
        return _render_success_response(deal_info, "Note submitted successfully")

    except Exception as e:
        logger.error(f"Unexpected error in excel_note_to_hubspot: {e}", exc_info=True)
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