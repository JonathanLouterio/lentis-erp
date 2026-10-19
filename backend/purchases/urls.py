from django.urls import path
from .views import PurchasesView, PurchaseDetailView

app_name='purchases'
urlpatterns=[path('me/purchases/',PurchasesView.as_view(),name='purchases'),path('me/purchases/<int:purchase_id>/',PurchaseDetailView.as_view(),name='purchase-detail')]
