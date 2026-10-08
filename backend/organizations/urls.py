from django.urls import path

from .views import (
    MyCustomerDetailView,
    MyCustomersView,
    MyProductDetailView,
    MyProductsView,
    MyStockMovementsView,
)

app_name = "organizations"

urlpatterns = [
    path("me/customers/", MyCustomersView.as_view(), name="my-customers"),
    path("me/customers/<int:customer_id>/", MyCustomerDetailView.as_view(), name="my-customer-detail"),
    path("me/products/", MyProductsView.as_view(), name="my-products"),
    path("me/products/<int:product_id>/", MyProductDetailView.as_view(), name="my-product-detail"),
    path("me/stock-movements/", MyStockMovementsView.as_view(), name="my-stock-movements"),
]
