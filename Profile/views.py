from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from core.authentication import CookieJWTAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from users.serializers import UserSerializer,SetUsersDetailsSerializer
from jobs.models import ServiceRequest
from .serializers import ServiceRequestHistorySerializer

class UserProfileView(APIView):
    """
    API endpoint to view and update user profile.
    """
    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Retrieve the authenticated user's profile.
        """
        user = request.user
        serializer = UserSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
class EditUserProfileView(APIView):
    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]
    def post(self, request):
        """
        Update the authenticated user's profile.
        """

        user = request.user
        serializer = SetUsersDetailsSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

class UserServiceRequestHistoryView(APIView):
    """
    API endpoint to view the user's service request history.
    """
    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Retrieve the authenticated user's service request history.
        """
        user = request.user
        service_requests = ServiceRequest.objects.filter(user=user)
        serializer = ServiceRequestHistorySerializer(service_requests, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)