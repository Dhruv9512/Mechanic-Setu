from django.urls import path
from .views import UpdateMechanicStatusView,GetBasicNeedsView

urlpatterns = [
   path('UpdateMechanicStatus/', UpdateMechanicStatusView.as_view(), name='UpdateMechanicStatus'),
   path('GetBasicNeeds/', GetBasicNeedsView.as_view(), name='GetBasicNeeds'),
]