from rest_framework import serializers
from .models import CustomUser

class SetUsersDetailsSerializer(serializers.ModelSerializer):
    """
    Serializer for updating user details.
    This serializer is specifically designed to allow users to update their own profile information.
    It excludes fields that should not be user-editable, such as 'is_mechanic' and 'id'.
    """
    class Meta:
        model = CustomUser
        # Only allow updating of certain fields to maintain data integrity and security.
        fields = ['first_name', 'last_name', 'mobile_number', 'profile_pic']
        read_only_fields = ['id', 'email']