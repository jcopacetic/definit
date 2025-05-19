from django.shortcuts import render
from django.http import HttpResponse

def hubspot_to_msgraph_webhook_listener(request):
    print(f"{vars(request)}")
    return HttpResponse(200)