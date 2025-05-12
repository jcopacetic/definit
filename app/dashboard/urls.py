from django.urls import path

from app.dashboard.views import dashboard_view
from app.dashboard.views import create_customer
from app.dashboard.views import get_customer

from app.dashboard.views import customer_view

app_name = "dashboard"

urlpatterns = [
    path("", view=dashboard_view, name="dashboard"),
    path("customer/<slug:customer_slug>/", view=customer_view, name="customer"),
    path("create-customer/", view=create_customer, name="create-customer"),
    path("get-customer/<slug:customer_slug>/", view=get_customer, name="get-customer"),
]