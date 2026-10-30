"""Entry points for the deployed React build and infrastructure health check."""
from django.conf import settings
from django.db import DatabaseError, connection
from django.http import FileResponse, HttpResponse, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe


class NoIndexMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        return response


@never_cache
@require_safe
def frontend(request):
    try:
        document = (settings.FRONTEND_DIST / "index.html").open("rb")
    except FileNotFoundError:
        return HttpResponse("Interface indisponível.", status=503, content_type="text/plain; charset=utf-8")
    return FileResponse(document, content_type="text/html; charset=utf-8")


@never_cache
@require_safe
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


@require_safe
def robots(request):
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")
