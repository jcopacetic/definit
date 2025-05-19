from django.urls import path 

from app.features.views import hubspot_to_msgraph_webhook_listener

app_name = "features"

url_patterns = [
    path("features/feature_1/hubspot/webhook/listener/", view=hubspot_to_msgraph_webhook_listener, name="hubspot_to_ms_graph_webhook")
]