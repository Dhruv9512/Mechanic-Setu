from rest_framework import serializers
from .models import Mechanic, ServiceRequest, CustomUser

class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for the CustomUser model.
    It exposes public-facing user information for use in other serializers.
    """
    class Meta:
        model = CustomUser
        fields = ['id', 'email', 'first_name', 'last_name', 'mobile_number', 'profile_pic', 'is_mechanic']


class MechanicSerializer(serializers.ModelSerializer):
    """
    Serializer for the Mechanic model.
    It includes nested data from the UserSerializer to provide complete mechanic details
    in a single API response, rather than just a user ID.
    
    """
    user = UserSerializer(read_only=True)

    class Meta:
        model = Mechanic
        fields = [
            'id', 'user', 'shop_name', 'shop_address', 'shop_latitude',
            'shop_longitude', 'status', 'is_verified'
        ]


class ServiceRequestSerializer(serializers.ModelSerializer):
    """
    Serializer for the ServiceRequest model.
    This is a key serializer that provides a comprehensive view of a job, including
    detailed information about the user who made the request and the mechanic assigned to it.
    """
    # By using the nested serializers, the API response for a ServiceRequest will contain
    # the full user and mechanic objects, which is highly efficient for frontends.
    requested_by = UserSerializer(read_only=True)
    mechanic = MechanicSerializer(read_only=True)

    class Meta:
        model = ServiceRequest
        fields = [
            'id', 'requested_by', 'mechanic', 'status', 'details', 'created_at'
        ]
        # These fields are controlled by the system (e.g., set on creation or through specific actions)
        # and should not be directly editable via a standard API payload.
        read_only_fields = ['id', 'created_at', 'requested_by', 'mechanic']

    def create(self, validated_data):
        """
        Overrides the default create method. This is a critical piece of business logic.
        It ensures that when a new service request is created via the API, it is automatically
        and securely assigned to the user who is currently logged in.
        """
        request = self.context.get('request', None)
        if request and hasattr(request, "user"):
            user = request.user
            # Enforce the business rule: A user who is registered as a mechanic cannot create a service request.
            if hasattr(user, 'mechanic_profile'):
                 raise serializers.ValidationError({"detail": "Mechanics are not permitted to create service requests."})
            # Create the ServiceRequest instance, linking it to the authenticated user.
            return ServiceRequest.objects.create(requested_by=user, **validated_data)

        # This case should ideally never be reached if the corresponding view has IsAuthenticated permission.
        # It's included as a safeguard.
        raise serializers.ValidationError({"detail": "Authentication credentials were not provided."})

