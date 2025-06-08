import logging
from django.shortcuts import render
from django.http import HttpResponse

from app.dashboard.models import Customer 

from app.ms_graph.client import MSGraphClient 
from app.hubspot.client import HubSpotClient

logger = logging.getLogger(__name__)

def excel_note_to_hubspot(request, excel_row):
    # set placeholder customer 
    customer = Customer.objects.first() 
    feature = customer.features.first()

    ms_client = MSGraphClient(customer)

    note_value = ms_client.get_cell_value_by_header(
        workbook_item_id=feature.workbook_id,
        worksheet_id=feature.worksheet_id,
        row_number = excel_row, 
        header_name = "Submit a Note",
    )

    if note_value:

        deal_id = ms_client.get_cell_value_by_header(
            workbook_item_id=feature.workbook_id,
            worksheet_id=feature.worksheet_id,
            row_number = excel_row, 
            header_name = "Record ID",
        )

        logger.info(f"\n\nrecord ID: {deal_id}\n\n")

        if deal_id:
            hs_client = HubSpotClient(customer.hubspot_secret_app_key)

            created_note = hs_client.create_note_on_deal(deal_id, note_value)

            if created_note:
                cell_update = ms_client.update_cell(
                    feature.workbook_id, 
                    feature.worksheet_id, 
                    f"J{excel_row}",
                    "",
                )

                logger.info(f"cell update: {cell_update}")

    

    return HttpResponse(status=200)
    