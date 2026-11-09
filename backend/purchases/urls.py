from .views import PurchaseAccessView, PurchaseOptionsView
from django.urls import path
from .views import PurchasesView, PurchaseDetailView

app_name='purchases'
urlpatterns=[path('me/purchases/access/',PurchaseAccessView.as_view()),path('me/purchases/options/',PurchaseOptionsView.as_view()),path('me/purchases/',PurchasesView.as_view(),name='purchases'),path('me/purchases/<int:purchase_id>/',PurchaseDetailView.as_view(),name='purchase-detail')]

from .payable_views import ExpenseCancelView, ExpenseCreateView, PayablesView, PayableDetailView, PayableOptionsView, PayablePaymentView, PayableReversalView
urlpatterns += [
    path('me/payables/', PayablesView.as_view(), name='payables'),
    path('me/payables/expenses/', ExpenseCreateView.as_view(), name='expense-create'),
    path('me/payables/expenses/<int:plan_id>/cancel/', ExpenseCancelView.as_view(), name='expense-cancel'),
    path('me/payables/options/', PayableOptionsView.as_view(), name='payable-options'),
    path('me/payables/<int:plan_id>/', PayableDetailView.as_view(), name='payable-detail'),
    path('me/payables/installments/<int:installment_id>/pay/', PayablePaymentView.as_view(), name='payable-payment'),
    path('me/payables/payments/<int:payment_id>/reverse/', PayableReversalView.as_view(), name='payable-reversal'),
]
