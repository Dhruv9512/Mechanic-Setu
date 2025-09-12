from django.urls import path
from .views import LoginView, OtpVerificationView, LogoutView


urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('otp-verify/', OtpVerificationView.as_view(), name='otp-verify'),
    path('logout/', LogoutView.as_view(), name='logout'),
]