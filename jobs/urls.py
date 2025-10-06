from django.urls import path
from .views import UpdateMechanicStatusView,GetBasicNeedsView,CreateServiceRequestView,AcceptServiceRequestView

urlpatterns = [
   path('UpdateMechanicStatus/', UpdateMechanicStatusView.as_view(), name='UpdateMechanicStatus'),
   path('GetBasicNeeds/', GetBasicNeedsView.as_view(), name='GetBasicNeeds'),
   path('CreateServiceRequest/', CreateServiceRequestView.as_view(), name='CreateServiceRequest'),
   path('AcceptServiceRequest/', AcceptServiceRequestView.as_view(), name='AcceptServiceRequest'),
]