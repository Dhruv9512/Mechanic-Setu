from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny

# Create your views here.
class LoginView(APIView):
    permission_classes = [AllowAny] 
    def post(self, request):
        # Implement your login logic here
        return Response({"message": "Login successful"}, status=status.HTTP_200_OK)
