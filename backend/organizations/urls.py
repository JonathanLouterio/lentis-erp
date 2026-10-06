from django.urls import path

from .views import MyCustomersView


app_name = "organizations"

urlpatterns = [
    path("me/customers/", MyCustomersView.as_view(), name="my-customers"),
]
