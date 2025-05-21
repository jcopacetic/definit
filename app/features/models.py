import uuid
import logging
from django.db import models
from django.utils.text import slugify
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from app.dashboard.models import Customer

from app.ms_graph.client import MSGraphClient
from app.hubspot.client import HubSpotClient

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


class CustomerFeature(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    slug = models.SlugField(max_length=255, unique=True, editable=False)

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="features")
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name="customer")

    workbook_id = models.CharField(max_length=280, blank=True)
    workbook_name = models.CharField(max_length=280, blank=True)
    worksheet_id = models.CharField(max_length=280, blank=True)
    worksheet_name = models.CharField(max_length=280, blank=True)
    worksheet_position = models.IntegerField(blank=True)
    worksheet_headers = models.JSONField(blank=True)
    worksheet_num_rows = models.PositiveIntegerField(blank=True)
    worksheet_num_columns = models.PositiveIntegerField(blank=True)
    worksheet_last_row = models.IntegerField(default=2)
    active = models.BooleanField(default=False, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.__class__.__name__}: ({self.slug})"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(str(self.uuid))
        super().save(*args, **kwargs)