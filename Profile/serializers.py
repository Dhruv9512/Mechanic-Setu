from rest_framework import serializers
from users.models import CustomUser
from jobs.models import ServiceRequest

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


class ServiceRequestHistorySerializer(serializers.ModelSerializer):
    """
    Serializer for the ServiceRequest model for user's history.
    """
    class Meta:
        model = ServiceRequest
        fields = [
            'id', 'status', 'latitude', 'longitude', 'location',
            'vehical_type', 'problem', 'additional_details', 'price',
            'cancellation_reason', 'created_at', 'updated_at'
        ]