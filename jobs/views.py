from uuid import uuid4
from django.conf import settings
from django.core.cache import cache
from vercel_blob import put
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from core.authentication import CookieJWTAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView


from users.models import Mechanic
from core.cache import cache_per_user, generate_user_cache_key
from django.utils.decorators import method_decorator

# View to update the status of a mechanic.
class UpdateMechanicStatusView(APIView):
    """
    View to update the status of a mechanic.
    Only accessible by admin users.
    """
    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def put(self, request):
        
        user_id = request.user.id
        new_status = request.data.get('status')

        if not user_id or not new_status:
            return Response({"error": "user_id and status are required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            mechanic = Mechanic.objects.get(user_id=user_id)
            mechanic.status = new_status
            mechanic.save()
            cache.delete(generate_user_cache_key(request))
            return Response({"message": "Mechanic status updated successfully."}, status=status.HTTP_200_OK)
        except Mechanic.DoesNotExist:
            return Response({"error": "Mechanic not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        


# View to get the basic needs of a mechanic.
@method_decorator(cache_per_user(60 * 5), name='dispatch')
class GetBasicNeedsView(APIView):
    """
    View to get the basic needs of a mechanic.
    Only accessible by authenticated users.
    """
    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_id = request.user.id

        if not user_id:
            return Response({"error": "user_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            mechanic = Mechanic.objects.get(user_id=user_id)
            basic_needs = {
                "first_name": mechanic.user.first_name,
                "last_name": mechanic.user.last_name,
                "shop_name": mechanic.shop_name,
                "status": mechanic.status,
                "is_verified": mechanic.is_verified,
            }
            return Response({"basic_needs": basic_needs}, status=status.HTTP_200_OK)
        except Mechanic.DoesNotExist:
            return Response({"error": "Mechanic not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)