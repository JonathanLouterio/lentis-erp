from django.urls import path

from .views import (
    MySaleCancelView, MySaleDetailView, MySaleFinalizeView,
    MySaleItemDetailView, MySaleItemsView, MySalesView,
)

from .payment_views import PaymentOptionsView, SaleCheckoutView, ReceivablesView, ReceiveInstallmentView, PaymentPreviewView

from .commercial_views import RequestDiscountView, DecideDiscountView

from .cash_views import CashSessionsView, CashDetailView, CashPostingsView, CashCloseView, CashOptionsView

from .dashboard_views import DashboardView

from .quote_views import QuotesView, QuoteDetailView, QuoteTransitionView

from .quote_print_views import QuotePrintView

from .prescription_views import PrescriptionAccessView, SalePrescriptionHistoryView

app_name = "sales"

urlpatterns = [
    path("me/sales/prescription-access/", PrescriptionAccessView.as_view(), name="sale-prescription-access"),
    path("me/sales/<int:sale_id>/prescription-history/", SalePrescriptionHistoryView.as_view(), name="sale-prescription-history"),
    path('me/quotes/<int:quote_id>/print/', QuotePrintView.as_view(), name='quote-print'),
    path('me/quotes/', QuotesView.as_view(), name='quotes'),
    path('me/quotes/<int:quote_id>/', QuoteDetailView.as_view(), name='quote-detail'),
    path('me/quotes/<int:quote_id>/<str:action>/', QuoteTransitionView.as_view(), name='quote-action'),
    path("me/dashboard/", DashboardView.as_view(), name="dashboard"),
    path('me/cash/options/', CashOptionsView.as_view(), name='cash-options'),
    path('me/cash/', CashSessionsView.as_view(), name='cash-sessions'),
    path('me/cash/<int:session_id>/', CashDetailView.as_view(), name='cash-detail'),
    path('me/cash/<int:session_id>/postings/', CashPostingsView.as_view(), name='cash-postings'),
    path('me/cash/<int:session_id>/close/', CashCloseView.as_view(), name='cash-close'),
    path("me/sales/payment-preview/", PaymentPreviewView.as_view(), name="payment-preview"),
    path("me/sales/<int:sale_id>/discount/request/", RequestDiscountView.as_view(), name="discount-request"),
    path("me/sales/<int:sale_id>/discount/<int:request_id>/decision/", DecideDiscountView.as_view(), name="discount-decision"),
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
