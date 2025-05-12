from django import forms
from app.dashboard.models import Customer

class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            "name", "domain", "hubspot_portal_id", "_hubspot_secret_app_key",
            "_msgraph_site_id", "_msgraph_drive_id", "_msgraph_client_id",
            "_msgraph_authority", "_msgraph_scopes",
        ]
        widgets = {
            field: forms.TextInput(attrs={"class": "form-control"})
            for field in fields
        }