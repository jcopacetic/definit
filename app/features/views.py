import logging
from django.shortcuts import render
from django.http import HttpResponse

logger = logging.getLogger(__name__)

def hubspot_to_msgraph_webhook_listener(request):
    logger.info(f"{vars(request)}")
    return HttpResponse(200)