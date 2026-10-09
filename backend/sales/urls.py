from django.urls import path

from .views import (
    MySaleCancelView, MySaleDetailView, MySaleFinalizeView,
    MySaleItemDetailView, MySaleItemsView, MySalesView,
)

from .payment_views import PaymentOptionsView, SaleCheckoutView, ReceivablesView, ReceiveInstallmentView

app_name = "sales"

urlpatterns = [
    path("me/sales/payment-options/", PaymentOptionsView.as_view(), name="payment-options"),
    path("me/sales/checkout/", SaleCheckoutView.as_view(), name="sale-checkout"),
    path("me/receivables/", ReceivablesView.as_view(), name="receivables"),
    path("me/receivables/<int:receivable_id>/receive/", ReceiveInstallmentView.as_view(), name="receive-installment"),
    path("me/sales/", MySalesView.as_view(), name="my-sales"),
    path("me/sales/<int:sale_id>/", MySaleDetailView.as_view(), name="sale-detail"),
    path("me/sales/<int:sale_id>/items/", MySaleItemsView.as_view(), name="sale-items"),
    path("me/sales/<int:sale_id>/items/<int:item_id>/", MySaleItemDetailView.as_view(), name="sale-item-detail"),
    path("me/sales/<int:sale_id>/finalize/", MySaleFinalizeView.as_view(), name="sale-finalize"),
    path("me/sales/<int:sale_id>/cancel/", MySaleCancelView.as_view(), name="sale-cancel"),
]
