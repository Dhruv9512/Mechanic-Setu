from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from phonenumber_field.modelfields import PhoneNumberField

# If you set up GeoDjango for advanced location features, uncomment the next line
# from django.contrib.gis.db import models as gis_models

# --- User Management ---

class CustomUserManager(BaseUserManager):
    """
    Custom manager for the CustomUser model where email is the unique identifier
    instead of a username.
    """
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password() # For social logins or passwordless flows
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractUser):
    """
    The primary user model for the application.
    """
    username = None  # Remove the default username field
    email = models.EmailField(unique=True)
    profile_pic = models.CharField(max_length=500, blank=True, null=True, default="")
    mobile_number = PhoneNumberField(blank=True, null=True, region="IN")
    
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []  # No extra fields required for createsuperuser command

    objects = CustomUserManager()

    def __str__(self):
        return self.email

# --- Application-Specific Models ---

class Mechanic(models.Model):
    """
    Extends the CustomUser model with mechanic-specific details and status.
    """
    class StatusChoices(models.TextChoices):
        OFFLINE = 'OFFLINE', 'Offline'
        ONLINE = 'ONLINE', 'Online'
        WORKING = 'WORKING', 'Working'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='mechanic_profile'
    )
    shop_name = models.CharField(max_length=255)
    shop_address = models.TextField()

    # Recommended: Use GeoDjango's PointField for efficient location queries.
    # shop_location = gis_models.PointField(null=True, blank=True)
    # Fallback: Simple latitude and longitude fields.
    shop_latitude = models.FloatField(null=True, blank=True)
    shop_longitude = models.FloatField(null=True, blank=True)

    is_verified = models.BooleanField(
        default=False,
        help_text="Designates whether the mechanic has been verified by an admin."
    )
    status = models.CharField(
        max_length=10,
        choices=StatusChoices.choices,
        default=StatusChoices.OFFLINE,
        help_text="The mechanic's current availability status."
    )

    def __str__(self):
        return f"{self.user.email} - {self.shop_name}"


class ServiceRequest(models.Model):
    """
    Represents a job request from a user to be fulfilled by a mechanic.
    """
    class StatusChoices(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        ACCEPTED = 'ACCEPTED', 'Accepted'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='service_requests'
    )
    mechanic = models.ForeignKey(
        Mechanic,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='jobs'
    )
    status = models.CharField(
        max_length=10,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDING
    )
    details = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Request from {self.requested_by.email} ({self.get_status_display()})"

