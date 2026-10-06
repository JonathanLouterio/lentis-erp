from django.urls import path

from .views import MyCustomerDetailView, MyCustomersView


app_name = "organizations"

urlpatterns = [
    path("me/customers/", MyCustomersView.as_view(), name="my-customers"),
    path(
        "me/customers/<int:customer_id>/",
        MyCustomerDetailView.as_view(),
        name="my-customer-detail",
    ),
]
