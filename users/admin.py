from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Mechanic, ServiceRequest

# --- Inlines ---

class MechanicProfileInline(admin.StackedInline):
    """
    Allows editing of the Mechanic model directly from the CustomUser admin page.
    This provides a convenient, unified view for users who are also mechanics.
    """
    model = Mechanic
    can_delete = False
    verbose_name_plural = 'Mechanic Profile'
    fk_name = 'user'

# --- ModelAdmin Configurations ---

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """
    Customizes the admin interface for the CustomUser model.
    It integrates mechanic profile management directly into the user view.
    """
    inlines = (MechanicProfileInline,)
    list_display = (
        "id", "email", "mobile_number", "is_mechanic", "profile_pic", "first_name",
        "last_name", "is_staff", "is_mechanic_verified"
    )
    list_filter = ("is_staff", "is_active", "is_superuser")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("email",)

    # Field layout for the user detail/edit page
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal Info", {"fields": ("first_name", "last_name", "mobile_number", "is_mechanic", "profile_pic")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important Dates", {"fields": ("last_login", "date_joined")}),
    )

    # Field layout for the user creation page
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "mobile_number", "is_mechanic", "profile_pic", "password", "is_staff", "is_active"),
        }),
    )
    list_select_related = ('mechanic_profile',)

    def get_inline_instances(self, request, obj=None):
        # Do not show the mechanic profile inline when creating a new user from scratch
        if not obj:
            return []
        return super().get_inline_instances(request, obj)

    @admin.display(description='Mechanic Verified?', boolean=True)
    def is_mechanic_verified(self, instance):
        """Custom method to display the mechanic's verification status in the user list."""
        if hasattr(instance, 'mechanic_profile') and instance.mechanic_profile:
            return instance.mechanic_profile.is_verified
        return False


@admin.register(Mechanic)
class MechanicAdmin(admin.ModelAdmin):
    """
    Customizes the admin interface specifically for the Mechanic model.
    """
    list_display = ('user', 'shop_name', 'status', 'is_verified')
    list_filter = ('status', 'is_verified')
    search_fields = ('user__email', 'shop_name', 'shop_address')
    actions = ['verify_mechanics']

    @admin.action(description='Mark selected mechanics as verified')
    def verify_mechanics(self, request, queryset):
        """Admin action to bulk-verify mechanics in one click."""
        count = queryset.update(is_verified=True)
        self.message_user(request, f"{count} mechanics were successfully verified.")


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

