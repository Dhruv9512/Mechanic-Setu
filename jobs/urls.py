from django.urls import path
from .views import UpdateMechanicStatusView

urlpatterns = [
   path('UpdateMechanicStatus/', UpdateMechanicStatusView.as_view(), name='UpdateMechanicStatus'),
]