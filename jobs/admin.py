from django.contrib import admin
from .models import ServiceRequest

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
        'cancellation_reason'
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