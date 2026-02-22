from django.db import models
from django.conf import settings
from users.models import Mechanic, CustomUser
import uuid


class ServiceRequest(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('ACCEPTED', 'Accepted'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
        ('EXPIRED', 'Expired'),
        ('ARRIVED', 'Arrived'),
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='service_requests')
    assigned_mechanic = models.ForeignKey(
        Mechanic, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='assigned_requests'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    # Location fields
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    location = models.CharField(max_length=255, blank=True, null=True) # User-provided address/location name
    vehical_type = models.CharField(max_length=100 ,blank=True, null=True)
    problem=models.TextField(blank=True, null=True) 
    additional_details=models.TextField(blank=True, null=True)
    price=models.FloatField(blank=True, null=True)
    cancellation_reason = models.TextField(blank=True, null=True) # New field
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    vehical_details = models.JSONField(blank= True, null=True)

    def __str__(self):
        return f"Request {self.id} for {self.vehical_type} by {self.user.email}"
    

class VehicleRCInfo(models.Model):
    # Vehicle Identification
    vehicle_id = models.CharField(max_length=20, unique=True)
    license_plate = models.CharField(max_length=20)
    chassis_number = models.CharField(max_length=50, null=True, blank=True)
    engine_number = models.CharField(max_length=50, null=True, blank=True)
    
    # Vehicle Details
    brand_name = models.CharField(max_length=255, null=True, blank=True)
    brand_model = models.CharField(max_length=255, null=True, blank=True)
    fuel_type = models.CharField(max_length=50, null=True, blank=True)
    color = models.CharField(max_length=50, null=True, blank=True)
    cubic_capacity = models.CharField(max_length=20, null=True, blank=True)
    cylinders = models.IntegerField(null=True, blank=True)
    seating_capacity = models.CharField(max_length=10, null=True, blank=True)
    vehicle_age = models.CharField(max_length=50, null=True, blank=True)
    vehicle_category = models.CharField(max_length=50, null=True, blank=True)
    vehicle_class = models.CharField(max_length=100, db_column='class', null=True, blank=True)
    norms = models.CharField(max_length=50, null=True, blank=True)
    
    # Owner Information
    owner_name = models.CharField(max_length=255, null=True, blank=True)
    father_name = models.CharField(max_length=255, null=True, blank=True)
    owner_count = models.CharField(max_length=10, null=True, blank=True)
    present_address = models.TextField(null=True, blank=True)
    permanent_address = models.TextField(null=True, blank=True)
    
    # Registration & Status
    registration_date = models.CharField(max_length=50, null=True, blank=True)
    rc_status = models.CharField(max_length=50, null=True, blank=True)
    source = models.CharField(max_length=100, null=True, blank=True)
    
    # Finance Details
    is_financed = models.CharField(max_length=10, null=True, blank=True)
    financer = models.CharField(max_length=255, null=True, blank=True)
    noc_details = models.CharField(max_length=255, null=True, blank=True)
    
    # API Metadata & Timestamps
    raw_response = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'vehicle_rc_info'

class UserVehicle(models.Model):
    user = models.ForeignKey('users.CustomUser', on_delete=models.CASCADE)
    vehicle = models.ForeignKey(VehicleRCInfo, to_field='vehicle_id', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    is_owner = models.BooleanField(default=False)
    notification_enabled = models.BooleanField(default=True)

    class Meta:
        db_table = 'user_vehicles'
        unique_together = ('user', 'vehicle')

