from django.urls import include, path

from .deployment_views import frontend, health, robots

urlpatterns = [
    path("healthz/", health, name="deployment-health"),
    path("robots.txt", robots),
    path("", frontend, name="frontend"),
    path("", include("config.urls")),
]
