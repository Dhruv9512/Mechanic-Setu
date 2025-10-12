from django.urls import path
from .views import UpdateMechanicStatusView,GetBasicNeedsView,CreateServiceRequestView,AcceptServiceRequestView,CancelServiceRequestView

urlpatterns = [
   path('UpdateMechanicStatus/', UpdateMechanicStatusView.as_view(), name='UpdateMechanicStatus'),
   path('GetBasicNeeds/', GetBasicNeedsView.as_view(), name='GetBasicNeeds'),
   path('CreateServiceRequest/', CreateServiceRequestView.as_view(), name='CreateServiceRequest'),
   path('AcceptServiceRequest/<int:request_id>/', AcceptServiceRequestView.as_view(), name='AcceptServiceRequest'),
   path('CancelServiceRequest/<int:request_id>/', CancelServiceRequestView.as_view(), name='CancelServiceRequest'),
]