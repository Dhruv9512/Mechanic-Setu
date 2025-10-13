from django.urls import path
from .views import UserProfileView,UserServiceRequestHistoryView,EditUserProfileView,MechanicProfileView,MechanicJobHistoryView



urlpatterns = [
    path('UserProfile/', UserProfileView.as_view(), name='User Profile'),
    path('EditUserProfile/', EditUserProfileView.as_view(), name='EditUser Profile'),
    path('UserHistory/', UserServiceRequestHistoryView.as_view(), name='User History'),
    path('MechanicProfile/', MechanicProfileView.as_view(), name='mechanic-profile'),
    path('MechanicHistory/', MechanicJobHistoryView.as_view(), name='mechanic-job-history'),
]