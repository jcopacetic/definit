import logging
from django.shortcuts import render
from django.http import HttpResponse

from app.dashboard.models import Customer 

from app.ms_graph.client import MSGraphClient 

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

    logger.info(f"\n\nnote value: {note_value}\n\n")

    return HttpResponse(status=200)
    