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

    def __str__(self):
        return f"Request {self.id} for {self.vehical_type} by {self.user.email}"