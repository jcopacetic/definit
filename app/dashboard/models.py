import uuid 
from django.db import models
from django.utils.text import slugify
from django.contrib.auth import get_user_model

from django.conf import settings 
from cryptography.fernet import Fernet, InvalidToken

from app.features.models import Feature

User = get_user_model()


class Dashboard(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    slug = models.SlugField(max_length=255, unique=True, editable=False)

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="dashboard")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email}'s dashboard"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(str(self.uuid))
        super().save(*args, **kwargs)










class Customer(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    slug = models.SlugField(max_length=255, unique=True, editable=False)

    features = models.ManyToManyField(Feature, blank=True, related_name="customers")

    dashboard = models.ForeignKey(Dashboard, on_delete=models.CASCADE, related_name="customers")
    name = models.CharField(max_length=80)
    domain = models.URLField(max_length=180)

    hubspot_portal_id = models.CharField(max_length=30, blank=True)
    _hubspot_secret_app_key = models.CharField(max_length=500, blank=True, db_column='hubspot_secret_app_key')

    # Encrypted Microsoft Graph fields
    _msgraph_site_id = models.CharField(max_length=500, blank=True, db_column='msgraph_site_id')
    _msgraph_drive_id = models.CharField(max_length=500, blank=True, db_column='msgraph_drive_id')
    _msgraph_client_id = models.CharField(max_length=500, blank=True, db_column='msgraph_client_id')
    _msgraph_client_secret = models.CharField(max_length=500, blank=True, db_column='msgraph_client_secret')
    _msgraph_tenant_id = models.CharField(max_length=500, blank=True, db_column='msgraph_tenant_id')
    _msgraph_authority = models.CharField(max_length=500, blank=True, db_column='msgraph_authority')
    _msgraph_scopes = models.CharField(max_length=500, blank=True, db_column='msgraph_scopes')

    _msgraph_access_token = models.CharField(max_length=500, blank=True, db_column="msgraph_access_token")
    _msgraph_refresh_token = models.CharField(max_length=500, blank=True, db_column="msgraph_refresh_token")
    _msgraph_access_token_expires_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.dashboard.user.email})"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(str(self.uuid))
        super().save(*args, **kwargs)
    
    def _encrypt_value(self, value):
        """Base method to encrypt a value using Fernet."""
        if not value:
            return ""
        
        f = Fernet(settings.FERNET_ENCRYPTION_KEY.encode())
        return f.encrypt(value.encode()).decode()
    
    def _decrypt_value(self, encrypted_value):
        """Base method to decrypt a value using Fernet."""
        if not encrypted_value:
            return ""
        
        try:
            f = Fernet(settings.FERNET_ENCRYPTION_KEY.encode())
            return f.decrypt(encrypted_value.encode()).decode()
        except (InvalidToken, ValueError):
            return "[decryption-error]"

    # HubSpot secret app key getter and setter
    @property
    def hubspot_secret_app_key(self):
        return self._decrypt_value(self._hubspot_secret_app_key)
    
    @hubspot_secret_app_key.setter
    def hubspot_secret_app_key(self, value):
        self._hubspot_secret_app_key = self._encrypt_value(value)
    
    # Microsoft Graph site ID getter and setter
    @property
    def msgraph_site_id(self):
        return self._decrypt_value(self._msgraph_site_id)
    
    @msgraph_site_id.setter
    def msgraph_site_id(self, value):
        self._msgraph_site_id = self._encrypt_value(value)
    
    # Microsoft Graph drive ID getter and setter
    @property
    def msgraph_drive_id(self):
        return self._decrypt_value(self._msgraph_drive_id)
    
    @msgraph_drive_id.setter
    def msgraph_drive_id(self, value):
        self._msgraph_drive_id = self._encrypt_value(value)
    
    # Microsoft Graph client ID getter and setter
    @property
    def msgraph_client_id(self):
        return self._decrypt_value(self._msgraph_client_id)
    
    @msgraph_client_id.setter
    def msgraph_client_id(self, value):
        self._msgraph_client_id = self._encrypt_value(value)

    # Microsoft Graph client secret getter and setter
    @property
    def msgraph_client_secret(self):
        return self._decrypt_value(self._msgraph_client_secret)
    
    @msgraph_client_secret.setter
    def msgraph_client_secret(self, value):
        self._msgraph_client_secret = self._encrypt_value(value)

    # Microsoft Graph tenant ID getter and setter
    @property
    def msgraph_tenant_id(self):
        return self._decrypt_value(self._msgraph_tenant_id)
    
    @msgraph_tenant_id.setter
    def msgraph_tenant_id(self, value):
        self._msgraph_tenant_id = self._encrypt_value(value)
    
    # Microsoft Graph authority getter and setter
    @property
    def msgraph_authority(self):
        return self._decrypt_value(self._msgraph_authority)
    
    @msgraph_authority.setter
    def msgraph_authority(self, value):
        self._msgraph_authority = self._encrypt_value(value)
    
    # Microsoft Graph scopes getter and setter
    @property
    def msgraph_scopes(self):
        return self._decrypt_value(self._msgraph_scopes)
    
    @msgraph_scopes.setter
    def msgraph_scopes(self, value):
        self._msgraph_scopes = self._encrypt_value(value)


  # --- Field checks ---
    def has_hubspot_secret(self):
        try:
            return bool(self.hubspot_secret_app_key and self.hubspot_secret_app_key != "[decryption-error]")
        except Exception:
            return False

    def has_msgraph_site_id(self):
        return bool(self.msgraph_site_id and self.msgraph_site_id != "[decryption-error]")

    def has_msgraph_drive_id(self):
        return bool(self.msgraph_drive_id and self.msgraph_drive_id != "[decryption-error]")

    def has_msgraph_client_id(self):
        return bool(self.msgraph_client_id and self.msgraph_client_id != "[decryption-error]")

    def has_msgraph_tenant_id(self):
        return bool(self.msgraph_tenant_id and self.msgraph_tenant_id != "[decryption-error]")

    def has_msgraph_authority(self):
        return bool(self.msgraph_authority and self.msgraph_authority != "[decryption-error]")

    def has_msgraph_scopes(self):
        return bool(self.msgraph_scopes and self.msgraph_scopes != "[decryption-error]")

    # --- Aggregate ---
    def connection_ready(self):
        """
        Determines if all required fields are available and decryptable.
        """
        return all([
            self.has_hubspot_secret(),
            self.has_msgraph_site_id(),
            self.has_msgraph_drive_id(),
            self.has_msgraph_client_id(),
            self.has_msgraph_tenant_id(),
            self.has_msgraph_scopes()
        ])

    def connection_checks(self):
        """
        Returns a dictionary of all checks (useful for UI).
        """
        return {
            "hubspot_secret_app_key": self.has_hubspot_secret(),
            "msgraph_site_id": self.has_msgraph_site_id(),
            "msgraph_drive_id": self.has_msgraph_drive_id(),
            "msgraph_client_id": self.has_msgraph_client_id(),
            "msgraph_tenant_id": self.has_msgraph_tenant_id(),
            "msgraph_scopes": self.has_msgraph_scopes(),
            "connection_ready": self.connection_ready(),
        }
