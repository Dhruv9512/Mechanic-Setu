from rest_framework import serializers
from users.models import CustomUser,Mechanic
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



class MechanicProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for the Mechanic model for the mechanic's own profile view.
    It includes nested data from the UserSerializer to provide complete mechanic details.
    """
    email = serializers.EmailField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    profile_pic = serializers.CharField(source='user.profile_pic', read_only=True)
    mobile_number = serializers.CharField(source='user.mobile_number', read_only=True)

    class Meta:
        model = Mechanic
        fields = [
            'id', 'email', 'first_name', 'last_name', 'profile_pic', 'mobile_number',
            'shop_name', 'shop_address', 'shop_latitude', 'shop_longitude',
            'status', 'is_verified', 'KYC_document', 'adhar_card'
        ]