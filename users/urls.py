from django.urls import path
from .views import Login_SignUpView, OtpVerificationView, LogoutView,Google_Login_SignupView,SetUsersDetail,ResendOtpView,SetMechanicDetailView,RejectMechanicView,GetMechanicDetailForVerifyView,VerifyMechanicView


urlpatterns = [
    path('Login_SignUp/', Login_SignUpView.as_view(), name='login'),
    path('otp-verify/', OtpVerificationView.as_view(), name='otp-verify'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('google/',Google_Login_SignupView.as_view(),name='Google Login/SignUp'),
    path('SetUsersDetail/',SetUsersDetail.as_view(),name='SetUsersDetail'),
    path('resend-otp/', ResendOtpView.as_view(), name='resend-otp'),
    path('SetMechanicDetail/', SetMechanicDetailView.as_view(), name='SetMechanicDetail'),
    path('RejectMechanic/', RejectMechanicView.as_view(), name='RejectMechanic'),
    path('GetMechanicDetailForVerify/', GetMechanicDetailForVerifyView.as_view(), name='GetMechanicDetailForVerify'),
    path('VerifyMechanic/', VerifyMechanicView.as_view(), name='VerifyMechanic'),

]