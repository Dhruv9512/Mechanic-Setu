from rest_framework import serializers
from .models import ServiceRequest
from users.models import Mechanic
from users.serializers import UserSerializer 

class JobDetailsForMechanicSerializer(serializers.ModelSerializer):
    """
    Provides the specific job and customer details a mechanic needs to see.
    """
    # Fields from the related user (customer)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    user_profile_pic = serializers.CharField(source='user.profile_pic', read_only=True)
    mobile_number = serializers.CharField(source='user.mobile_number', read_only=True)

    class Meta:
        model = ServiceRequest
        fields = [
            'id', 'status', 'latitude', 'longitude', 'location',
            'vehical_type', 'problem', 'additional_details',
            'first_name', 'last_name', 'user_profile_pic', 'mobile_number'
        ]

class MechanicDataForUserSerializer(serializers.ModelSerializer):
    """
    Provides the specific mechanic details a user needs to see.
    """
    # Fields from the related user (the mechanic's user profile)
    id = serializers.IntegerField(source='user.id', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    phone_number = serializers.CharField(source='user.mobile_number', read_only=True)
    Mechanic_profile_pic = serializers.CharField(source='user.profile_pic', read_only=True)

    class Meta:
        model = Mechanic
        fields = [
            'id', 'first_name', 'last_name', 'phone_number',
            'current_latitude', 'current_longitude', 'Mechanic_profile_pic'
        ]
