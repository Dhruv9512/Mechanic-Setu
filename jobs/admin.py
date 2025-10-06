from django.contrib import admin
from .models import ServiceRequest
# Register your models here.
@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    """
    Customizes the admin interface for the ServiceRequest model.
    """
    list_display = ('id', 'requested_by', 'mechanic', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('id', 'requested_by__email', 'mechanic__user__email', 'details')
    readonly_fields = ('id', 'created_at')

    # Organize the service request detail view into logical sections
    fieldsets = (
        ('Request Details', {
            'fields': ('id', 'details', 'status', 'created_at')
        }),
        ('Assignment Information', {
            'fields': ('requested_by', 'mechanic')
        }),
    )

