from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        """
        Create and return a regular user with email instead of username.
        """
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        extra_fields.setdefault("is_active", True)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)  # set password if provided
        else:
            user.set_unusable_password()  # for Google login users
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """
        Create and return a superuser.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractUser):
    username = None  # remove username
    email = models.EmailField(unique=True)

    # ✅ Add profile_pic
    profile_pic = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        default=""
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []  # removes username from createsuperuser prompt

    objects = CustomUserManager()

    def __str__(self):
        return self.email
