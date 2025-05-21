import logging
import json
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.template.loader import render_to_string

from app.dashboard.models import Dashboard
from app.dashboard.models import Customer 
from app.features.models import CustomerFeature, Feature

from app.ms_graph.client import MSGraphClient
from app.hubspot.client import HubSpotClient

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
def sidepanel_handler(request, panel_html, extra_html="", open=False):
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
        extra_class = "" if not open else "active"
        template = render_to_string(
            "snippets/sidepanel.html",
            {
                "control_class": extra_class,
                "panel_action": panel_html,
            }
        )
    if request.method == "DELETE":
        extra_class = "" if not open else "active"
        template = render_to_string(
            "snippets/sidepanel.html",
            {
                "control_class": extra_class,
                "panel_action": panel_html,
            }
        )
    html_response = template + extra_html
    
    return HttpResponse(html_response, status=200)




ALLOWED_STEPS = {0, 1, 2, 3, 4, 5}
ALLOWED_FEATURES = {"feature_1"}

@login_required
def customer_feature_handler(request, customer_slug):
    step = int(request.headers.get("x-step", "100"))
    logger.info(f"step: {step}")
    feature = request.headers.get("x-feature", "")
    logger.info(f"feature: {feature}")

    if step not in ALLOWED_STEPS:
        logger.error("Invalid step value received: %s", step)
        return HttpResponse(status=403)

    if feature not in ALLOWED_FEATURES:
        logger.error("Invalid feature value received: %s", feature)
        return HttpResponse(status=403)

    customer = get_object_or_404(Customer, slug=customer_slug)
    ms_client = MSGraphClient(customer)

    panel_action = ""
    extra_html = ""
    open=False
    sidepanel_payload = {"customer_slug": customer_slug}

    if request.method == "GET":
        if feature == "feature_1" and step == 1:
            logger.info("Fetching workbooks for feature_1, step 1")
            try:
                workbooks = ms_client.get_workbooks()
                session_key = f"{customer_slug}_feature_1_workbooks"

                workbooks_field = [
                    {"name": wb.get("name", ""), "id": wb.get("id", ""), "position": wb.get("position", "")}
                    for wb in workbooks
                ]
                sidepanel_payload["workbooks"] = workbooks_field
                
                request.session[session_key] = sidepanel_payload["workbooks"]
                request.session.modified = True

            except Exception as e:
                logger.exception("Failed to retrieve workbooks: %s", e)
                return HttpResponse(status=500)

            panel_action = render_to_string(
                "snippets/sidepanel/add_feature_to_customer.html",
                sidepanel_payload,
            )

    elif request.method == "POST":
        if feature == "feature_1" and step == 1:
            try:
                workbook_id = request.POST.get("workbook-select", "")
                logger.info(f"Received workbook_id from POST: {workbook_id}")

                selected_wb_key = f"{customer_slug}_feature_1_workbook_id"
                if workbook_id:
                    request.session[selected_wb_key] = workbook_id
                    request.session.modified = True
                    logger.info(f"Stored workbook_id in session under key: {selected_wb_key}")

                workbooks_key = f"{customer_slug}_feature_1_workbooks"
                workbook_options = request.session.get(workbooks_key)
                if not workbook_options:
                    logger.warning(f"No workbook list in session under key: {workbooks_key}")
                    return HttpResponse(status=400)

                logger.info(f"Session workbook_options: {workbook_options}")

                # Lookup the workbook name by ID
                selected_wb = next((wb for wb in workbook_options if wb["id"] == workbook_id), None)
                if not selected_wb:
                    logger.error(f"No matching workbook found for ID: {workbook_id}")
                    return HttpResponse(status=404)

                selected_wb_name = selected_wb.get("name", "Unnamed Workbook")
                logger.info(f"Selected workbook name: {selected_wb_name}")

                selected_wb_name_key = f"{customer_slug}_feature_1_workbook_name"
                if selected_wb_name:
                    request.session[selected_wb_name_key] = selected_wb_name
                    request.session.modified = True
                    logger.info(f"Stored workbook_name in session under key: {selected_wb_name_key}")

                worksheets = ms_client.get_worksheets(workbook_id)
                session_ws_key = f"{customer_slug}_feature_1_worksheets"

                worksheets_field = [
                    {"name": ws.get("name", ""), "id": ws.get("id", ""), "position": ws.get("position", "")}
                    for ws in worksheets
                ]
                sidepanel_payload["worksheets"] = worksheets_field
                sidepanel_payload["raw"] = worksheets

                request.session[session_ws_key] = sidepanel_payload["worksheets"]
                request.session.modified = True

                panel_action = render_to_string(
                "snippets/sidepanel/add_feature_to_customer_step_2.html",
                    sidepanel_payload,
                )
                open = True

            except json.JSONDecodeError:
                logger.error("Invalid JSON in request body")
                return HttpResponse(status=400)
            
        
        if feature == "feature_1" and step == 2:
            try: 
                worksheet_id = request.POST.get("worksheet-select")
                logger.info(f"Received worksheet_id from POST: {worksheet_id}")

                selected_ws_key = f"{customer_slug}_feature_1_worksheet_id"
                if worksheet_id:
                    request.session[selected_ws_key] = worksheet_id
                    request.session.modified = True
                    logger.info(f"Stored worksheet_id in session under key: {selected_ws_key}")

                worksheets_key = f"{customer_slug}_feature_1_worksheets"
                worksheet_options = request.session.get(worksheets_key)
                if not worksheet_options:
                    logger.warning(f"No worksheet list in session under key: {worksheets_key}")
                    return HttpResponse(status=400)
                
                logger.info(f"session worksheet_options: {worksheet_options}")

                selected_ws = next((ws for ws in worksheet_options if ws["id"] == worksheet_id), None)
                if not selected_ws: 
                    logger.error(f"No matching worksheet found for ID: {worksheet_id}")
                    return HttpResponse(status=404)
                
                selected_ws_name = selected_ws.get("name", "unnamed worksheet")
                logger.info(f"Selected worksheet name: {selected_ws_name}")

                selected_ws_name_key = f"{customer_slug}_feature_1_worksheet_name"
                if selected_ws_name:
                    request.session[selected_ws_name_key] = selected_ws_name 
                    request.session.modified = True 
                    logger.info(f"Stored worksheet_name in session under key: {selected_ws_name_key}")

                selected_ws_position = selected_ws.get("position", "")
                logger.info(f"Selected worksheet position: {selected_ws_position}")

                selected_ws_position_key = f"{customer_slug}_feature_1_worksheet_position"
                if selected_ws_position_key: 
                    request.session[selected_ws_position_key] = selected_ws_position
                    request.session.modified = True 
                    logger.info(f"Stored worksheet_position in session under key: {selected_ws_position_key}")

                selected_wb_key = f"{customer_slug}_feature_1_workbook_id"
                workbook_id = request.session.get(selected_wb_key)

                worksheet_headers = ms_client.get_worksheet_headers(workbook_id, worksheet_id)

                worksheet_headers_key = f"{customer_slug}_feature_1_worksheet_headers"
                if worksheet_headers: 
                    request.session[worksheet_headers_key] = worksheet_headers
                    request.session.modified = True 
                    logger.info(f"Stored worksheet_position in session under key: {worksheet_headers_key}")

                sidepanel_payload["headers"] = worksheet_headers 

                worksheet_dimensions = ms_client.get_worksheet_dimensions(workbook_id, worksheet_id)

                worksheet_dimensions_key = f"{customer_slug}_feature_1_worksheet_dimensions"
                if worksheet_dimensions: 
                    request.session[worksheet_dimensions_key] = worksheet_dimensions
                    request.session.modified = True 
                    logger.info(f"Stored worksheet_position in session under key: {worksheet_dimensions_key}")

                sidepanel_payload["dimensions"] = worksheet_dimensions

                worksheet_last_row = ms_client.get_last_row(workbook_id, worksheet_id)

                worksheet_last_row_key = f"{customer_slug}_feature_1_worksheet_last_row"
                if worksheet_last_row: 
                    request.session[worksheet_last_row_key] = worksheet_last_row
                    request.session.modified = True 
                    logger.info(f"Stored worksheet_position in session under key: {worksheet_last_row_key}")

                sidepanel_payload["last_row"] = worksheet_last_row 
                
                
                panel_action = render_to_string(
                "snippets/sidepanel/add_feature_to_customer_step_3.html",
                    sidepanel_payload,
                )
                open = True

            except json.JSONDecodeError: 
                logger.error("Invalid JSON in request body")
                return HttpResponse(status=400)


        if feature == "feature_1" and step == 3:
            try: 
                selected_wokbook_id_key = f"{customer_slug}_feature_1_workbook_id"
                workbook_id = request.session.get(selected_wokbook_id_key)

                selected_workbook_name_key = f"{customer_slug}_feature_1_workbook_name"
                workbook_name = request.session.get(selected_workbook_name_key)

                selected_worksheet_id_key = f"{customer_slug}_feature_1_worksheet_id"
                worksheet_id = request.session.get(selected_worksheet_id_key)

                selected_worksheet_name_key = f"{customer_slug}_feature_1_worksheet_name"
                worksheet_name = request.session.get(selected_worksheet_name_key)

                selected_worksheet_position_key = f"{customer_slug}_feature_1_worksheet_position"
                worksheet_position = request.session.get(selected_worksheet_position_key)

                worksheet_headers_key = f"{customer_slug}_feature_1_worksheet_headers"
                worksheet_headers = request.session.get(worksheet_headers_key)

                worksheet_dimensions_key = f"{customer_slug}_feature_1_worksheet_dimensions"
                worksheet_dimensions = request.session.get(worksheet_dimensions_key)

                worksheet_last_row_key = f"{customer_slug}_feature_1_worksheet_last_row"
                worksheet_last_row = request.session.get(worksheet_last_row_key)

                CustomerFeature.objects.create(
                    customer = customer,
                    feature = Feature.objects.first(),
                    workbook_id = workbook_id, 
                    workbook_name = workbook_name,
                    worksheet_id = worksheet_id, 
                    worksheet_name = worksheet_name, 
                    worksheet_position = worksheet_position, 
                    worksheet_headers = worksheet_headers, 
                    worksheet_num_rows = worksheet_dimensions[0],
                    worksheet_num_columns = worksheet_dimensions[1],
                    worksheet_last_row = worksheet_last_row,
                    active = True, 
                )

            except json.JSONDecodeError: 
                logger.error("Invalid JSON in request body")
                return HttpResponse(status=400)
    elif request.method == "DELETE":
        logger.info("DELETE request received for customer %s, feature %s", customer_slug, feature)
        # Future DELETE logic here

    else:
        return HttpResponse(status=405)

    return sidepanel_handler(request, panel_action, extra_html, open)




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
        if data.get("hubspot_client_secret"):
            customer.hubspot_client_secret = data["hubspot_client_secret"]
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
        if data.get("hubspot_client_secret"):
            customer.hubspot_client_secret = data["hubspot_client_secret"]
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


@login_required
def get_api_response(request, customer_slug):
    customer = get_object_or_404(Customer, slug=customer_slug, dashboard=request.user.dashboard)
    
    panel_action = ""
    extra_html = ""
    action = request.headers.get("X-Function")

    if action in [
        "get-sites",
        "get-site-by-name",
        "get-site-by-path", 
        "get-drives", 
        "get-drive-by-name",
        "get-drive-items", 
        "get-folder-items",
        "search-items",
        "get-item",
        "get-item-by-id",
        "get-workbooks",
        "get-workbook-by-name",
        "get-worksheets",
        "get-worksheet-by-name",
        "get-worksheet-by-index",
        "get-range",
        "get-used-range",
        "get-worksheet-headers",
        "get-column-letter-by-header",
        "find-row-by-value",
        "update-cell",
        "update-range",
        "append-row",
        "get-last-row",
        "get-worksheet-dimensions",
        "find-row-by-id",
        "create-worksheet",
        "get-file", 
        "get-file-content"
    ]:
        ms_client = MSGraphClient(customer)

    if action in [
        "get-all-owners",
        "get-owner",
        "get-deal",
        "get-contact",
        "get-company",
        "get-email",
        "get-note",
        "get-engagement",
        "update-deal",
        "get-all-deals",
        "get-contacts-by-deal-id",
        "get-companies-by-deal-id",
        "get-emails-by-deal-id",
        "get-notes-by-deal-id",
        "get-tasks-by-deal-id",
        "get-quotes-by-deal-id",
        "get-deal-associated-quotes",
        "get-deal-associated-contacts",
        "get-deal-associated-companies",
        "get-deal-associated-engagements",
        "get-most-recent-deal-associated-engagements",
        "latest-deal-quote-public-url-key",
        "create-note",
        "associate-objects",
        "search-objects",
        "collect-and-parse-deal-data",
    ]:
        hs_client = HubSpotClient(customer.hubspot_secret_app_key) 

    if request.method == "GET":
        json_data_to_display = []
        raw_json_data = []
        
        # MICROSOFT GRAPH FUNCTIONS

        if action == "get-sites":
            raw_json_data = ms_client.get_sites()

        if action == "get-site-by-name": 
            site_name = request.GET.get("site_name")
            raw_json_data = ms_client.get_site_by_name(site_name)

        if action == "get-site-by-path":
            site_path = request.GET.get("site_path")
            raw_json_data = ms_client.get_site_by_path(site_path)

        if action == "get-drives":
            raw_json_data = ms_client.get_drives() 

        if action == "get-drive-by-name":
            drive_name = request.GET.get("drive_name")
            raw_json_data = ms_client.get_drive_by_name(drive_name)
        
        if action == "get-drive-items":
            raw_json_data = ms_client.get_drive_items()

        if action == "get-folder-items":
            folder_path = request.GET.get("folder_path")
            raw_json_data = ms_client.get_folder_items(folder_path)

        if action == "search-items":
            search_term = request.GET.get("search_term")
            raw_json_data = ms_client.search_items(search_term)

        if action == "get-item":
            item_path = request.GET.get("item_path")
            raw_json_data = ms_client.get_item(item_path)

        if action == "get-item-by-id":
            item_id = request.GET.get("item_id")
            raw_json_data = ms_client.get_item_by_id(item_id)

        if action == "get-workbooks":
            folder_path = request.GET.get("folder_path")
            raw_json_data = ms_client.get_workbooks(folder_path)

        if action == "get-workbook-by-name":
            workbook_name = request.GET.get("workbook_name")
            folder_path = request.GET.get("folder_path")
            raw_json_data = ms_client.get_workbook_by_name(workbook_name, folder_path)

        if action == "get-worksheets":
            workbook_item_id = request.GET.get("workbook_item_id")
            raw_json_data = ms_client.get_worksheets(workbook_item_id)
        
        if action == "get-worksheet-by-name":
            workbook_item_id = request.GET.get("workbook_item_id")
            worksheet_name = request.GET.get("worksheet_name")
            raw_json_data = ms_client.get_worksheet_by_name(workbook_item_id, worksheet_name)

        if action == "get-worksheet-by-index":
            workbook_item_id = request.GET.get("workbook_item_id")
            worksheet_index = request.GET.get("worksheet_index")
            raw_json_data = ms_client.get_worksheet_by_index(workbook_item_id, worksheet_index)

        if action == "get-range":
            workbook_item_id = request.GET.get("workbook_item_id")
            worksheet_id = request.GET.get("worksheet_id")
            range_address = request.GET.get("range_address")
            raw_json_data = ms_client.get_range(workbook_item_id, worksheet_id, range_address)

        if action == "get-used-range":
            workbook_item_id = request.GET.get("workbook_item_id")
            worksheet_id = request.GET.get("worksheet_id")
            raw_json_data = ms_client.get_used_range(workbook_item_id, worksheet_id)

        if action == "get-worksheet-headers":
            workbook_item_id = request.GET.get("workbook_item_id")
            worksheet_id = request.GET.get("worksheet_id")
            header_row = int(request.GET.get("header_row"))
            raw_json_data = ms_client.get_worksheet_headers(workbook_item_id, worksheet_id, header_row)

        if action == "get-column-index-by-header":
            workbook_item_id = request.GET.get("workbook_item_id")
            worksheet_id = request.GET.get("worksheet_id")
            header_name = request.GET.get("header_name")
            header_row = int(request.GET.get("header_row"))
            raw_json_data = ms_client.get_column_index_by_header(workbook_item_id, worksheet_id, header_name, header_row)        

        if action == "get-column-letter-by-header":
            workbook_item_id = request.GET.get("workbook_item_id")
            worksheet_id = request.GET.get("worksheet_id")
            header_name = request.GET.get("header_name")
            header_row = int(request.GET.get("header_row"))
            raw_json_data = ms_client.get_column_letter_by_header(workbook_item_id, worksheet_id, header_name, header_row) 
        
        if action == "find-row-by-value":
            workbook_item_id = request.GET.get("workbook_item_id")
            worksheet_id = request.GET.get("worksheet_id")
            column = request.GET.get("column")
            search_term = request.GET.get("search_term")
            case_sensitive = True if request.GET.get("case_sensitive") == "true" else False
            raw_json_data = ms_client.find_row_by_value(workbook_item_id, worksheet_id, column, search_term, case_sensitive) 

        if action == "update-cell":
            workbook_item_id = request.GET.get("workbook_item_id")
            worksheet_id = request.GET.get("worksheet_id")
            cell_address = request.GET.get("cell_address")
            cell_value = request.GET.get("cell_value")
            raw_json_data = ms_client.update_cell(workbook_item_id, worksheet_id, cell_address, cell_value) 

        if action == "update-range":
            workbook_item_id = request.GET.get("workbook_item_id")
            worksheet_id = request.GET.get("worksheet_id")
            range_address = request.GET.get("range_address")
            range_values_list = request.GET.get("range_values_list")
            raw_json_data = ms_client.update_range(workbook_item_id, worksheet_id, range_address, range_values_list) 
        
        if action == "append-row":
            workbook_item_id = request.GET.get("workbook_item_id")
            worksheet_id = request.GET.get("worksheet_id")
            row_values_list = request.GET.get("row_values_list")
            raw_json_data = ms_client.append_row(workbook_item_id, worksheet_id, row_values_list) 
        
        if action == "get-last-row":
            workbook_item_id = request.GET.get("workbook_item_id")
            worksheet_id = request.GET.get("worksheet_id")
            raw_json_data = ms_client.get_last_row(workbook_item_id, worksheet_id) 

        if action == "get-worksheet-dimensions":
            workbook_item_id = request.GET.get("workbook_item_id")
            worksheet_id = request.GET.get("worksheet_id")
            raw_json_data = ms_client.get_worksheet_dimensions(workbook_item_id, worksheet_id) 

        if action == "find-row-by-id":
            workbook_item_id = request.GET.get("workbook_item_id")
            worksheet_id = request.GET.get("worksheet_id")
            id_column = request.GET.get("id_column")
            id_value = request.GET.get("id_value")
            raw_json_data = ms_client.find_row_by_id(workbook_item_id, worksheet_id, id_column, id_value) 

        if action == "create-worksheet":
            workbook_item_id = request.GET.get("workbook_item_id")
            new_worksheet_name = request.GET.get("new_worksheet_name")
            raw_json_data = ms_client.create_worksheet(workbook_item_id, new_worksheet_name) 

        if action == "get-file":
            file_name = request.GET.get("file_name")
            raw_json_data = ms_client.get_file(file_name)

        if action == "get-file-content":
            file_name = request.GET.get("file_name")
            raw_json_data = ms_client.get_file_content(file_name)
        


        # HUBSPOT FUNCTIONS
        if action == "get-all-owners":
            raw_json_data = hs_client.get_all_owners()

        if action == "get-owner":
            owner_id = request.GET.get("owner_id")
            raw_json_data = hs_client.get_owner(owner_id)

        if action == "get-deal":
            deal_id = request.GET.get("deal_id")
            deal_properties = request.GET.get("deal_properties") if request.GET.get("deal_properties") else None
            print(f"Deal ID: {deal_id}, Deal Properties: {deal_properties}")
            raw_json_data = hs_client.get_deal(deal_id, deal_properties)

        if action == "get-contact":
            contact_id = request.GET.get("contact_id")
            contact_properties = request.GET.get("contact_properties")
            raw_json_data = hs_client.get_contact(contact_id, contact_properties)

        if action == "get-company":
            company_id = request.GET.get("company_id")
            company_properties = request.GET.get("company_properties")
            raw_json_data = hs_client.get_company(company_id, company_properties)

        if action == "get-email":
            email_id = request.GET.get("email_id")
            email_properties = request.GET.get("email_properties")
            raw_json_data = hs_client.get_email(email_id, email_properties)

        if action == "get-note":
            note_id = request.GET.get("note_id")
            note_properties = request.GET.get("note_properties")
            raw_json_data = hs_client.get_note(note_id, note_properties)

        if action == "get-engagement":
            engagement_id = request.GET.get("engagement_id")
            raw_json_data = hs_client.get_engagement(engagement_id)

        if action == "update-deal":
            deal_id = request.GET.get("deal_id")
            deal_properties = request.GET.get("deal_properties")
            raw_json_data = hs_client.update_deal(deal_id, deal_properties)

        if action == "get-all-deals":
            properties = request.GET.get("deals_properties")
            limit = request.GET.get("deals_limit")
            raw_json_data = hs_client.get_deals(properties, limit)

        if action == "get-contacts-by-deal-id":
            deal_id = request.GET.get("deal_id")
            raw_json_data = hs_client.get_contacts_by_deal(deal_id)

        if action == "get-companies-by-deal-id":
            deal_id = request.GET.get("deal_id")
            raw_json_data = hs_client.get_companies_by_deal(deal_id)

        if action == "get-emails-by-deal-id":
            deal_id = request.GET.get("deal_id")
            raw_json_data = hs_client.get_emails_by_deal(deal_id)

        if action == "get-notes-by-deal-id":
            deal_id = request.GET.get("deal_id")
            raw_json_data = hs_client.get_notes_by_deal(deal_id)

        if action == "get-tasks-by-deal-id":
            deal_id = request.GET.get("deal_id")
            raw_json_data = hs_client.get_tasks_by_deal(deal_id)

        if action == "get-quotes-by-deal-id":
            deal_id = request.GET.get("deal_id")
            raw_json_data = hs_client.get_quotes_by_deal(deal_id)

        if action == "get-deal-associated-quotes":
            deal_id = request.GET.get("deal_id")
            raw_json_data = hs_client.get_deal_associated_quotes(deal_id)

        if action == "get-deal-associated-contacts":
            deal_id = request.GET.get("deal_id")
            raw_json_data = hs_client.get_deal_associated_contacts(deal_id)

        if action == "get-deal-associated-companies":
            deal_id = request.GET.get("deal_id")
            primary = request.get.get("primary_only")
            raw_json_data = hs_client.get_deal_associated_companies(deal_id, primary)
            
        if action == "get-deal-associated-engagements":
            deal_id = request.GET.get("deal_id")
            raw_json_data = hs_client.get_deal_associated_engagements(deal_id) 

        if action == "get-most-recent-deal-associated-engagements":
            deal_id = request.GET.get("deal_id")
            raw_json_data = hs_client.find_most_recent_engagement(deal_id)

        if action == "latest-deal-quote-public-url-key":
            deal_id = request.GET.get("deal_id")
            raw_json_data = hs_client.get_latest_quote_public_url_key(deal_id)

        if action == "create-note":
            pass 

        if action == "associate-objects":
            pass  

        if action == "search-objects":
            pass 

        if action == "collect-and-parse-deal-data":
            limit = request.GET.get("deals_limit")
            raw_json_data = hs_client.collect_parse_deal_data(limit)

        if raw_json_data:
            json_data_to_display = json.dumps(raw_json_data, indent=2)

        panel_action = render_to_string(
            "snippets/sidepanel/function_test_response.html",
            {
                "title": f"API Response: {action}",
                "json_data_to_display": json_data_to_display,
                "customer_slug": customer.slug,
            }
        )

    if request.method in ["GET", "DELETE"]:
        return sidepanel_handler(request, panel_action, extra_html)
    return HttpResponse(status=403)


