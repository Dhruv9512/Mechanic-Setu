from django.contrib import admin
from .models import ServiceRequest,VehicleRCInfo, UserVehicle

@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    """
    Customizes the admin interface for the ServiceRequest model.
    """
    # --- MODIFIED: All fields are now included in the list display ---
    list_display = (
        'id', 
        'user', 
        'assigned_mechanic', 
        'status', 
        'vehical_type', 
        'location', 
        'price',
        'created_at',
        'updated_at',
        'cancellation_reason',
        'vehical_details'
    )
    
    # Filters available on the right sidebar
    list_filter = ('status', 'vehical_type', 'created_at')
    
    # Fields that can be searched
    search_fields = (
        'id__icontains', 
        'user__email', 
        'assigned_mechanic__user__email', 
        'vehical_type', 
        'location'
    )
    
    # Fields that cannot be edited directly in the admin panel
    readonly_fields = ('id', 'created_at', 'updated_at')

    # --- MODIFIED: All fields are now organized into fieldsets ---
    fieldsets = (
        ('Core Information', {
            'fields': ('id', 'status', 'price')
        }),
        ('User and Mechanic', {
            'fields': ('user', 'assigned_mechanic')
        }),
        ('Vehicle and Problem Details', {
            'fields': ('vehical_type', 'problem', 'additional_details')
        }),
        ('Location Information', {
            'fields': ('location', 'latitude', 'longitude')
        }),
        ('Cancellation Information', {
            'fields': ('cancellation_reason',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    # Make foreign key fields searchable with a dropdown/search box
    raw_id_fields = ('user', 'assigned_mechanic')

@admin.register(VehicleRCInfo)
class VehicleRCInfoAdmin(admin.ModelAdmin):
    """
    Manages the master database of vehicle registration details.
    """
    list_display = (
        'vehicle_id', 
        'license_plate', 
        'owner_name', 
        'brand_name', 
        'brand_model', 
        'rc_status', 
        'created_at'
    )
    list_filter = ('rc_status', 'fuel_type', 'vehicle_category', 'is_financed')
    search_fields = ('vehicle_id', 'license_plate', 'owner_name', 'chassis_number')
    readonly_fields = ('created_at', 'updated_at', 'last_synced_at', 'raw_response')
    
    fieldsets = (
        ('Identification', {
            'fields': ('vehicle_id', 'license_plate', 'chassis_number', 'engine_number')
        }),
        ('Technical Details', {
            'fields': (
                'brand_name', 'brand_model', 'vehicle_category', 'vehicle_class',
                'fuel_type', 'color', 'cubic_capacity', 'cylinders', 'norms'
            )
        }),
        ('Ownership & Registration', {
            'fields': (
                'owner_name', 'father_name', 'owner_count', 
                'registration_date', 'rc_status', 'vehicle_age'
            )
        }),
        ('Address Information', {
            'fields': ('present_address', 'permanent_address')
        }),
        ('Financials', {
            'fields': ('is_financed', 'financer', 'noc_details')
        }),
        ('Metadata', {
            'classes': ('collapse',),
            'fields': ('source', 'raw_response', 'created_at', 'updated_at', 'last_synced_at')
        }),
    )

@admin.register(UserVehicle)
class UserVehicleAdmin(admin.ModelAdmin):
    """
    Tracks which users have saved which vehicles for quick access or notifications.
    """
    list_display = ('user', 'vehicle', 'is_owner', 'notification_enabled', 'created_at')
    list_filter = ('is_owner', 'notification_enabled')
    search_fields = ('user__email', 'user__mobile_number', 'vehicle__vehicle_id')
    raw_id_fields = ('user', 'vehicle')
