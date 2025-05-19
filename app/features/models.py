import uuid
import logging
from django.db import models
from django.utils.text import slugify
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from app.ms_graph.client import MSGraphClient

logger = logging.getLogger(__name__)

class FeatureCategory(models.Model):
    """
    Categories to organize features by their purpose or domain
    """
    name = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    
    class Meta:
        verbose_name_plural = "Feature Categories"
    
    def __str__(self):
        return self.name


class FeatureStatus(models.TextChoices):
    """
    Status options for features
    """
    DRAFT = 'draft', 'Draft'
    ACTIVE = 'active', 'Active'
    DEPRECATED = 'deprecated', 'Deprecated'
    DISABLED = 'disabled', 'Disabled'


class BaseFeature(models.Model):
    """
    Abstract base model for all features providing common fields and behaviors
    """
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    slug = models.SlugField(max_length=255, unique=True, editable=False)
    
    name = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    
    # Feature metadata
    status = models.CharField(max_length=20, choices=FeatureStatus.choices, default=FeatureStatus.DRAFT)
    categories = models.ManyToManyField(FeatureCategory, blank=True, related_name="%(class)s_features")
    version = models.CharField(max_length=20, default="1.0.0")
    
    # Access control
    is_public = models.BooleanField(default=False, help_text="Whether this feature is publicly available")
    requires_authentication = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = True
    
    def __str__(self):
        return f"{self.__class__.__name__}: {self.name} ({self.slug})"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(str(self.uuid))
        super().save(*args, **kwargs)
    
    def is_available(self):
        """Check if the feature is available for use"""
        return self.status == FeatureStatus.ACTIVE


class Feature(BaseFeature):
    """
    Concrete implementation of the base feature model
    This can be used directly or inherited for specific feature types
    """
    # Additional fields specific to all concrete features
    icon = models.CharField(max_length=50, blank=True, help_text="Font awesome icon name")
    priority = models.IntegerField(default=0, help_text="Priority order (higher numbers appear first)")
    
    # Feature configuration
    config = models.JSONField(default=dict, blank=True, help_text="General configuration options stored as JSON")
    
    class Meta:
        ordering = ['-priority', 'name']


class FeatureDependency(models.Model):
    """
    Model to track dependencies between features
    """
    # The feature that has a dependency
    dependent_feature_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, 
                                              related_name='dependent_features')
    dependent_feature_id = models.UUIDField()
    dependent_feature = GenericForeignKey('dependent_feature_type', 'dependent_feature_id')
    
    # The feature that is required
    required_feature_type = models.ForeignKey(ContentType, on_delete=models.CASCADE,
                                             related_name='required_for_features')
    required_feature_id = models.UUIDField()
    required_feature = GenericForeignKey('required_feature_type', 'required_feature_id')
    
    # Dependency type
    DEPENDENCY_TYPES = [
        ('required', 'Required'),
        ('optional', 'Optional'),
        ('incompatible', 'Incompatible'),
    ]
    dependency_type = models.CharField(max_length=20, choices=DEPENDENCY_TYPES, default='required')
    
    class Meta:
        verbose_name_plural = "Feature Dependencies"
        unique_together = [
            ['dependent_feature_type', 'dependent_feature_id', 
             'required_feature_type', 'required_feature_id']
        ]
    
    def __str__(self):
        return f"{self.dependent_feature} {self.dependency_type} {self.required_feature}"


# ===== Specific Feature Types =====

# class IntegrationFeature(Feature):
#     """Base class for features that integrate with external systems"""
#     api_key = models.CharField(max_length=255, blank=True)
#     base_url = models.URLField(blank=True)
#     api_version = models.CharField(max_length=20, blank=True)
#     last_sync = models.DateTimeField(null=True, blank=True)
    
#     class Meta:
#         abstract = True


# class DataTransformFeature(Feature):
#     """Base class for features that transform data from one format to another"""
#     source_format = models.CharField(max_length=50)
#     target_format = models.CharField(max_length=50)
#     transformation_schema = models.JSONField(default=dict)
    
#     class Meta:
#         abstract = True


# ===== Concrete Feature Implementations =====

class HubSpotToExcelSheet(Feature):
    """Feature that exports HubSpot data to Excel spreadsheets"""
    workbook_id = models.CharField(max_length=280, blank=True)
    workbook_name = models.CharField(max_length=280, blank=True)
    worksheet_id = models.CharField(max_length=280, blank=True)
    worksheet_position = models.IntegerField(blank=True)
    worksheet_name = models.CharField(max_length=280, blank=True)
    file_name = models.CharField(max_length=280, blank=True)
    file_id = models.CharField(max_length=280, blank=True)
    last_row = models.IntegerField(default=2)

    # 1. - lookup workspace by file name
    def find_workspace(self, customer):
        """Find and set the file ID by looking up the file name in Microsoft SharePoint"""
        try:
            ms_client = MSGraphClient(customer)
            
            file_id = ms_client.get_file(self.file_name)
            if file_id:
                self.file_id = file_id
                self.save(update_fields=['file_id'])
                logger.info(f"Found file ID: {file_id} for {self.file_name}")
                return True
            else:
                logger.error(f"File '{self.file_name}' not found")
                return False
        except Exception as e:
            logger.exception(f"Error finding workspace: {e}")
            return False
    
    # 2. - lookup worksheet position
    def lookup_worksheet(self, customer):
        """Get the worksheet ID based on the position specified"""
        try:
            if not self.file_id:
                logger.error("File ID not set. Run find_workspace first.")
                return False
                
            ms_client = MSGraphClient(customer)
            access_token = ms_client.get_access_token()
            
            worksheet_name = ms_client.get_worksheet(self.file_id, self.worksheet_position, access_token)
            if worksheet_name and "Error" not in worksheet_name:
                self.worksheet_id = worksheet_name
                self.save(update_fields=['worksheet_id'])
                logger.info(f"Found worksheet: {worksheet_name} at position {self.worksheet_position}")
                return True
            else:
                logger.error(f"Worksheet at position {self.worksheet_position} not found or error: {worksheet_name}")
                return False
        except Exception as e:
            logger.exception(f"Error looking up worksheet: {e}")
            return False
    
    # 3. - gather columns
    def gather_columns(self, customer):
        """Fetch the column headers from the Excel sheet to map to HubSpot properties"""
        try:
            if not self.file_id or not self.worksheet_id:
                logger.error("File ID or Worksheet ID not set. Run previous steps first.")
                return False
                
            ms_client = MSGraphClient(customer)
            access_token = ms_client.get_access_token()
            
            # Get the header row (first row)
            range_address = 'A1:Z1'  # Adjust as needed for your column count
            url = f"{ITEMS_PATH}/{self.file_id}/workbook/worksheets/{self.worksheet_id}/range(address='{range_address}')"
            
            headers = {"Authorization": f"Bearer {access_token}"}
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            header_data = response.json().get('values', [[]])[0]
            
            # Filter out empty headers
            columns = [header for header in header_data if header]
            
            # Find the last populated row for future updates
            last_row = manual_last_row_finder(self.file_id, self.worksheet_id, access_token)
            if last_row:
                self.last_row = last_row + 1  # Set to next available row
                self.save(update_fields=['last_row'])
            
            logger.info(f"Found {len(columns)} columns: {columns}")
            logger.info(f"Last row is: {self.last_row}")
            
            return columns
        except Exception as e:
            logger.exception(f"Error gathering columns: {e}")
            return []
    
    # 4. - set columns to hubspot values
    def map_columns_to_hubspot(self, columns):
        """Map Excel columns to HubSpot properties"""
        hubspot_mapping = {}
        hubspot_properties = []
        
        # Common property mappings for different HubSpot object types
        common_mappings = {
            'deals': {
                'Deal ID': 'dealId',
                'Deal Name': 'dealname',
                'Amount': 'amount',
                'Deal Stage': 'dealstage',
                'Deal Owner': 'hubspot_owner_id',
                'Create Date': 'createdate',
                'Close Date': 'closedate',
                'City': 'city',
                'State': 'state',
                'Last Contacted': 'notes_last_contacted',
                'Last Contacted Type': 'notes_last_contacted_type',
                'Last Engagement': 'notes_last_engagement',
                'Last Engagement Type': 'notes_last_engagement_type',
            },
            'contacts': {
                'Contact ID': 'hs_object_id',
                'First Name': 'firstname',
                'Last Name': 'lastname',
                'Email': 'email',
                'Phone': 'phone',
                'Company': 'company',
                'Job Title': 'jobtitle',
                'Owner': 'hubspot_owner_id',
                'Create Date': 'createdate',
                'Last Activity': 'lastmodifieddate',
            },
            'companies': {
                'Company ID': 'hs_object_id',
                'Company Name': 'name',
                'Domain': 'domain',
                'Industry': 'industry',
                'City': 'city',
                'State': 'state',
                'Phone': 'phone',
                'Owner': 'hubspot_owner_id',
                'Create Date': 'createdate',
            },
            'tickets': {
                'Ticket ID': 'hs_object_id',
                'Subject': 'subject',
                'Description': 'content',
                'Status': 'hs_ticket_status',
                'Priority': 'hs_ticket_priority',
                'Create Date': 'createdate',
                'Owner': 'hubspot_owner_id',
            }
        }
        
        mappings = common_mappings.get(self.hubspot_object_type, {})
        
        for column in columns:
            hubspot_property = mappings.get(column, None)
            if hubspot_property:
                hubspot_mapping[column] = hubspot_property
                hubspot_properties.append(hubspot_property)
            else:
                # Try to make a reasonable guess for property name
                suggested_property = column.lower().replace(' ', '_')
                hubspot_mapping[column] = suggested_property
                hubspot_properties.append(suggested_property)
        
        # Update the model with the list of properties to fetch
        self.hubspot_properties = hubspot_properties
        self.save(update_fields=['hubspot_properties'])
        
        logger.info(f"Mapped {len(hubspot_mapping)} columns to HubSpot properties")
        return hubspot_mapping
    
    # 5. - turn on feature
    def setup_feature(self, customer):
        """Complete setup of the HubSpot to Excel feature"""
        try:
            # Step 1: Find workspace/file
            if not self.file_id and not self.find_workspace(customer):
                return False
            
            # Step 2: Get worksheet
            if not self.worksheet_id and not self.lookup_worksheet(customer):
                return False
            
            # Step 3: Gather columns
            columns = self.gather_columns(customer)
            if not columns:
                return False
            
            # Step 4: Map columns to HubSpot properties
            hubspot_mapping = self.map_columns_to_hubspot(columns)
            if not hubspot_mapping:
                return False
            
            # Feature is now set up and ready to use
            logger.info(f"HubSpot to Excel feature set up successfully for {self.file_name}")
            return True
            
        except Exception as e:
            logger.exception(f"Error setting up HubSpot to Excel feature: {e}")
            return False
    
    def update_excel_with_hubspot_data(self, customer, hubspot_id=None):
        """Update Excel with HubSpot data"""
        try:
            if not self.file_id or not self.worksheet_id:
                logger.error("Feature not fully set up. Run setup_feature first.")
                return False
            
            ms_client = MSGraphClient(customer)
            access_token = ms_client.get_access_token()
            
            # Get the HubSpot client
            hubspot_client = HubSpotClient(customer)
            
            # Get data from HubSpot
            if hubspot_id:
                # Get a specific object
                data = hubspot_client.get_object(self.hubspot_object_type, hubspot_id, self.hubspot_properties)
                if not data:
                    logger.error(f"No data found for {self.hubspot_object_type} ID {hubspot_id}")
                    return False
                
                # Check if this ID already exists in the Excel sheet
                excel_row = id_row_lookup(hubspot_id, self.file_id, self.worksheet_id, self.last_row, access_token)
                
                if excel_row:
                    # Update existing row
                    row_to_update = excel_row
                else:
                    # Add to next available row
                    row_to_update = self.last_row
                    self.last_row += 1
                    self.save(update_fields=['last_row'])
            else:
                # Get multiple objects (could be paginated)
                data_list = hubspot_client.get_objects(self.hubspot_object_type, properties=self.hubspot_properties, limit=10)
                if not data_list:
                    logger.error(f"No data found for {self.hubspot_object_type}")
                    return False
                
                # Process each object
                for idx, data in enumerate(data_list):
                    hubspot_id = data.get('id')
                    excel_row = id_row_lookup(hubspot_id, self.file_id, self.worksheet_id, self.last_row, access_token)
                    
                    if excel_row:
                        row_to_update = excel_row
                    else:
                        row_to_update = self.last_row + idx
                
                # Update the last row for next time
                self.last_row = row_to_update + len(data_list)
                self.save(update_fields=['last_row'])
                
                # For simplicity, let's just handle the first item for now
                data = data_list[0]
                row_to_update = self.last_row - len(data_list)
            
            # Format data for Excel update
            formatted_data = self.format_data_for_excel(data)
            
            # Update the Excel sheet
            result = edit_spreadsheet_using_api(
                self.file_id,
                self.worksheet_id,
                formatted_data,
                row_to_update,
                access_token
            )
            
            logger.info(f"Updated Excel with HubSpot data at row {row_to_update}")
            return True
            
        except Exception as e:
            logger.exception(f"Error updating Excel with HubSpot data: {e}")
            return False
    
    def format_data_for_excel(self, hubspot_data):
        """Format HubSpot data for Excel update"""
        # This will need to be customized based on your specific needs
        formatted_data = {
            "deal_id": hubspot_data.get("id", ""),
            "name": hubspot_data.get("properties", {}).get("dealname", ""),
            "deal_link": f"https://app.hubspot.com/contacts/YOUR_PORTAL_ID/deal/{hubspot_data.get('id', '')}",
            "plans_link": "",  # You'll need to customize this
            "city": hubspot_data.get("properties", {}).get("city", ""),
            "state": hubspot_data.get("properties", {}).get("state", ""),
            "associated_contact": "",  # You'll need to get associated contact data
            "associated_company": hubspot_data.get("properties", {}).get("company", ""),
            "deal_stage": hubspot_data.get("properties", {}).get("dealstage", ""),
            "deal_owner": hubspot_data.get("properties", {}).get("hubspot_owner_id", ""),
            "deal_amount": hubspot_data.get("properties", {}).get("amount", ""),
            "quote_link": "",  # You'll need to customize this
            "last_contacted": hubspot_data.get("properties", {}).get("notes_last_contacted", ""),
            "last_contacted_type": hubspot_data.get("properties", {}).get("notes_last_contacted_type", ""),
            "last_engagement": hubspot_data.get("properties", {}).get("notes_last_engagement", ""),
            "last_engagement_type": hubspot_data.get("properties", {}).get("notes_last_engagement_type", ""),
            "email": "",  # Engagement count fields - you'll need to get these
            "call": "",
            "meeting": "",
            "note": "",
            "task": ""
        }
        
        return formatted_data



class ScheduledFeature(models.Model):
    """
    Mixin for features that need to run on a schedule
    """
    schedule_type = models.CharField(max_length=20, choices=[
        ('manual', 'Manual'),
        ('interval', 'Interval-based'),
        ('cron', 'Cron Expression'),
    ], default='manual')
    
    # For interval-based scheduling
    interval_value = models.IntegerField(default=1)
    interval_unit = models.CharField(max_length=10, choices=[
        ('minutes', 'Minutes'),
        ('hours', 'Hours'),
        ('days', 'Days'),
        ('weeks', 'Weeks'),
    ], default='days')
    
    # For cron-based scheduling
    cron_expression = models.CharField(max_length=100, blank=True)
    
    # Common scheduling fields
    last_run = models.DateTimeField(null=True, blank=True)
    next_run = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        abstract = True


# Example of a scheduled HubSpot feature
class ScheduledHubSpotExport(HubSpotToExcelSheet, ScheduledFeature):
    """HubSpot to Excel export that runs on a schedule"""
    max_records = models.IntegerField(default=1000)
    
    def get_next_run_time(self):
        """Calculate the next run time based on scheduling settings"""
        # Implementation would depend on your scheduling logic
        pass


# ===== Feature Configuration =====

class FeatureSetting(models.Model):
    """
    Store settings for features that need to be configurable without code changes
    """
    feature_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    feature_id = models.UUIDField()
    feature = GenericForeignKey('feature_type', 'feature_id')
    
    key = models.CharField(max_length=100)
    value_type = models.CharField(max_length=20, choices=[
        ('string', 'String'),
        ('integer', 'Integer'),
        ('float', 'Float'),
        ('boolean', 'Boolean'),
        ('json', 'JSON'),
    ])
    string_value = models.TextField(blank=True, null=True)
    integer_value = models.IntegerField(blank=True, null=True)
    float_value = models.FloatField(blank=True, null=True)
    boolean_value = models.BooleanField(blank=True, null=True)
    json_value = models.JSONField(blank=True, null=True)
    
    class Meta:
        unique_together = ['feature_type', 'feature_id', 'key']
    
    def __str__(self):
        return f"{self.feature} - {self.key}"
    
    @property
    def value(self):
        """Return the appropriate value based on value_type"""
        if self.value_type == 'string':
            return self.string_value
        elif self.value_type == 'integer':
            return self.integer_value
        elif self.value_type == 'float':
            return self.float_value
        elif self.value_type == 'boolean':
            return self.boolean_value
        elif self.value_type == 'json':
            return self.json_value
        return None