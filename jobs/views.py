from uuid import uuid4
from django.conf import settings
from django.core.cache import cache
from vercel_blob import put
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated , IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView


from users.models import Mechanic


# 
class UpdateMechanicStatusView(APIView):
    """
    View to update the status of a mechanic.
    Only accessible by admin users.
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        mechanic_id = request.data.get('mechanic_id')
        new_status = request.data.get('status')

        if not mechanic_id or not new_status:
            return Response({"error": "mechanic_id and status are required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            mechanic = Mechanic.objects.get(id=mechanic_id)
            mechanic.status = new_status
            mechanic.save()
            return Response({"message": "Mechanic status updated successfully."}, status=status.HTTP_200_OK)
        except Mechanic.DoesNotExist:
            return Response({"error": "Mechanic not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)