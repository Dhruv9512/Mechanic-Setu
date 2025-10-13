from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from core.authentication import CookieJWTAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from users.serializers import UserSerializer,SetUsersDetailsSerializer
from jobs.models import ServiceRequest,Mechanic
from .serializers import ServiceRequestHistorySerializer,MechanicProfileSerializer
from django.db.models import Sum, Count
from datetime import date, timedelta

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



class MechanicProfileView(APIView):
    """
    API endpoint for a mechanic to view their own profile.
    """
    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            mechanic = request.user.mechanic_profile
            serializer = MechanicProfileSerializer(mechanic)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Mechanic.DoesNotExist:
            return Response({"error": "Mechanic profile not found."}, status=status.HTTP_404_NOT_FOUND)


class MechanicJobHistoryView(APIView):
    """
    API endpoint to view the mechanic's job history and statistics.
    """
    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            mechanic = request.user.mechanic_profile
        except Mechanic.DoesNotExist:
            return Response({"error": "Mechanic profile not found."}, status=status.HTTP_404_NOT_FOUND)

        today = date.today()
        start_of_month = today.replace(day=1)

        # Base queryset for completed jobs
        completed_jobs = ServiceRequest.objects.filter(
            assigned_mechanic=mechanic,
            status='COMPLETED'
        )

        # Calculate statistics
        total_earnings = completed_jobs.aggregate(total_earnings=Sum('price'))['total_earnings'] or 0
        jobs_this_month = completed_jobs.filter(created_at__gte=start_of_month).count()
        total_jobs = completed_jobs.count()

        today_start = today
        today_end = today + timedelta(days=1)
        today_jobs_qs = completed_jobs.filter(created_at__range=(today_start, today_end))
        today_earnings = today_jobs_qs.aggregate(today_earnings=Sum('price'))['today_earnings'] or 0
        today_jobs = today_jobs_qs.count()

        # Get job history
        job_history = ServiceRequest.objects.filter(assigned_mechanic=mechanic).order_by('-created_at')
        job_history_serializer = ServiceRequestHistorySerializer(job_history, many=True)

        response_data = {
            'statistics': {
                'total_earnings': total_earnings,
                'jobs_this_month': jobs_this_month,
                'total_jobs': total_jobs,
                'today_earnings': today_earnings,
                'today_jobs': today_jobs,
            },
            'job_history': job_history_serializer.data
        }

        return Response(response_data, status=status.HTTP_200_OK)