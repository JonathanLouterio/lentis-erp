from django.urls import path

from .auth_views import (
    CurrentUserView,
    csrf_token_view,
    login_view,
    logout_view,
)
from .views import MyStoresView

from .auth_views import (
    CurrentUserView,
    UserPreferencesView,
    csrf_token_view,
    login_view,
    logout_view,
)

app_name = "accounts"

urlpatterns = [
    path("me/", CurrentUserView.as_view(), name="me"),
    path("me/stores/", MyStoresView.as_view(), name="my-stores"),
    path("auth/csrf/", csrf_token_view, name="csrf"),
    path("auth/login/", login_view, name="login"),
    path("auth/logout/", logout_view, name="logout"),
    path("me/preferences/",UserPreferencesView.as_view(),name="my-preferences",),
]