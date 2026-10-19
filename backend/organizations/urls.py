from django.urls import path

from .views import (
    MyCustomerDetailView,
    MyCustomersView,
    MyProductDetailView,
    MyProductsView,
    MyStockMovementsView,
)

from .prescription_api import PrescriptionsView, PrescriptionDetailView, PrescriptionArchiveView

from .customer_history_api import CustomerHistoryView

app_name = "organizations"

urlpatterns = [
    path("me/customers/<int:customer_id>/history/", CustomerHistoryView.as_view(), name="customer-history"),
    path("me/prescriptions/", PrescriptionsView.as_view(), name="prescriptions"),
    path("me/prescriptions/<int:record_id>/", PrescriptionDetailView.as_view(), name="prescription-detail"),
    path("me/prescriptions/<int:record_id>/archive/", PrescriptionArchiveView.as_view(), name="prescription-archive"),
    path("me/customers/", MyCustomersView.as_view(), name="my-customers"),
    path("me/customers/<int:customer_id>/", MyCustomerDetailView.as_view(), name="my-customer-detail"),
    path("me/products/", MyProductsView.as_view(), name="my-products"),
    path("me/products/<int:product_id>/", MyProductDetailView.as_view(), name="my-product-detail"),
    path("me/stock-movements/", MyStockMovementsView.as_view(), name="my-stock-movements"),
]
