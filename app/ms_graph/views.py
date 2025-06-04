import logging
from django.shortcuts import render
from django.http import HttpResponse

logger = logging.getLogger(__name__)

def excel_note_to_hubspot(request, excel_row):
    logger.info(dir(request))
    return HttpResponse(status=200)
    