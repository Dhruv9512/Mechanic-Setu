from django.urls import path
from .views import Login_SignUpView, OtpVerificationView, LogoutView


urlpatterns = [
    path('Login_SignUp/', Login_SignUpView.as_view(), name='login'),
    path('otp-verify/', OtpVerificationView.as_view(), name='otp-verify'),
    path('logout/', LogoutView.as_view(), name='logout'),
]