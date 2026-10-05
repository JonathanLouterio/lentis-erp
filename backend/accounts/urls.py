from django.urls import path

from .views import MyStoresView


app_name = "accounts"

urlpatterns = [
    path("me/stores/", MyStoresView.as_view(), name="my-stores"),
]