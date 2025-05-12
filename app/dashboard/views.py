import logging
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.template.loader import render_to_string

from app.dashboard.models import Dashboard
from app.dashboard.models import Customer 

logger = logging.getLogger(__name__)

@login_required
def dashboard_view(request):
    user = request.user
    dashboard = get_object_or_404(Dashboard, user=user)
    return render(request, "dashboard/dashboard.html", {"dashboard": dashboard})


@login_required 
def customer_view(request, customer_slug):
    user = request.user
    dashboard = get_object_or_404(Dashboard, user=user)
    customer = get_object_or_404(Customer, dashboard=dashboard, slug=customer_slug)
    return render(request, "dashboard/customer.html", {"customer": customer})

@login_required 
def sidepanel_handler(request, panel_html, extra_html=""):
    if request.method in ["GET", "PUT"]:
        extra_class = "active"
        template = render_to_string(
            "snippets/sidepanel.html",
            {
                "control_class": extra_class,
                "panel_action": panel_html,
            }
        )

    if request.method == "POST":
        extra_class = ""
        template = render_to_string(
            "snippets/sidepanel.html",
            {
                "control_class": extra_class,
                "panel_action": panel_html,
            }
        )
    if request.method == "DELETE":
        extra_class = ""
        template = render_to_string(
            "snippets/sidepanel.html",
            {
                "control_class": extra_class,
                "panel_action": panel_html,
            }
        )
    html_response = template + extra_html
    
    return HttpResponse(html_response, status=200)



@login_required
def create_customer(request):
    panel_action = render_to_string(
        "snippets/sidepanel/create_customer_action.html",
    )
    extra_html = ""

    if request.method == "POST":
        data = request.POST
        customer, _ = Customer.objects.get_or_create(
            dashboard=request.user.dashboard,
            domain=data.get("domain"),
            defaults={
                "name": data.get("name"),
                "hubspot_portal_id": data.get("hubspot_portal_id"),
            }
        )

        # Encrypted fields are assigned via their property
        if data.get("hubspot_secret_app_key"):
            customer.hubspot_secret_app_key = data["hubspot_secret_app_key"]
        if data.get("msgraph_site_id"):
            customer.msgraph_site_id = data["msgraph_site_id"]
        if data.get("msgraph_drive_id"):
            customer.msgraph_drive_id = data["msgraph_drive_id"]
        if data.get("msgraph_client_id"):
            customer.msgraph_client_id = data["msgraph_client_id"]
        if data.get("msgraph_client_secret"):
            customer.msgraph_client_secret = data["msgraph_client_secret"]
        if data.get("msgraph_tenant_id"):
            customer.msgraph_tenant_id = data["msgraph_tenant_id"]
        if data.get("msgraph_authority"):
            customer.msgraph_authority = data["msgraph_authority"]
        if data.get("msgraph_scopes"):
            customer.msgraph_scopes = data["msgraph_scopes"]

        customer.save()

        extra_html = render_to_string(
            "dashboard/snippets/customers_table.html",
            {"customers": request.user.dashboard.customers.all()}
        )

    return sidepanel_handler(request, panel_action, extra_html)

@login_required
def get_customer(request, customer_slug):
    customer = get_object_or_404(Customer, slug=customer_slug)
    extra_html = ""
    method = request.POST.get("_method", request.method)

    if method == "GET":
        panel_action = render_to_string(
            "snippets/sidepanel/view_customer.html",
            {"customer": customer}
        )
    if method == "PUT":
        panel_action = render_to_string(
            "snippets/sidepanel/edit_customer.html",
            {"customer": customer}
        )
    if method == "POST":
        data = request.POST
        logger.info(f"Updating customer {customer.slug} with data: {data.dict()}")

        customer.name = data.get("name", customer.name)
        customer.domain = data.get("domain", customer.domain)
        customer.hubspot_portal_id = data.get("hubspot_portal_id", customer.hubspot_portal_id)

        # Encrypted properties
        if data.get("hubspot_secret_app_key"):
            customer.hubspot_secret_app_key = data["hubspot_secret_app_key"]
        if data.get("msgraph_site_id"):
            customer.msgraph_site_id = data["msgraph_site_id"]
        if data.get("msgraph_drive_id"):
            customer.msgraph_drive_id = data["msgraph_drive_id"]
        if data.get("msgraph_client_id"):
            customer.msgraph_client_id = data["msgraph_client_id"]
        if data.get("msgraph_client_secret"):
            customer.msgraph_client_secret = data["msgraph_client_secret"]
        if data.get("msgraph_tenant_id"):
            customer.msgraph_tenant_id = data["msgraph_tenant_id"]
        if data.get("msgraph_authority"):
            customer.msgraph_authority = data["msgraph_authority"]
        if data.get("msgraph_scopes"):
            customer.msgraph_scopes = data["msgraph_scopes"]

        customer.save()
        logger.info(f"Customer {customer.slug} updated successfully.")

        panel_action = render_to_string(
            "snippets/sidepanel/view_customer.html",
            {"customer": customer}
        )

        extra_html = render_to_string(
            "dashboard/snippets/customers_table.html",
            {"customers": request.user.dashboard.customers.all()}
        )
    if request.method == "DELETE":
        panel_action = ""
    if request.method in ["GET", "PUT", "POST", "DELETE"]:
        return sidepanel_handler(request, panel_action, extra_html)
    return HttpResponse(status=403)