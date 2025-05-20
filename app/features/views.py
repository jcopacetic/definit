import logging
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse

logger = logging.getLogger(__name__)


@csrf_exempt
def hubspot_to_msgraph_webhook_listener(request):
    logger.info(f"{vars(request)}")
    return HttpResponse(200)