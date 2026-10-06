import json

from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import IsAuthenticated

from .serializers import CurrentUserSerializer


@never_cache
@require_GET
@ensure_csrf_cookie
def csrf_token_view(request):
    return JsonResponse({"csrfToken": get_token(request)})


@method_decorator(never_cache, name="dispatch")
class CurrentUserView(RetrieveAPIView):
    serializer_class = CurrentUserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


@never_cache
@require_POST
@csrf_protect
def login_view(request):
    if request.content_type != "application/json":
        return JsonResponse(
            {"detail": "Envie os dados em application/json."},
            status=415,
        )

    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse(
            {"detail": "JSON inválido."},
            status=400,
        )

    if not isinstance(data, dict):
        return JsonResponse(
            {"detail": "Envie um objeto com usuário e senha."},
            status=400,
        )

    username = data.get("username")
    password = data.get("password")

    if not isinstance(username, str) or not isinstance(password, str):
        return JsonResponse(
            {"detail": "Usuário e senha devem ser textos."},
            status=400,
        )

    username = username.strip()

    if not username or not password:
        return JsonResponse(
            {"detail": "Informe usuário e senha."},
            status=400,
        )

    user = authenticate(
        request,
        username=username,
        password=password,
    )

    if user is None or not user.is_active:
        return JsonResponse(
            {"detail": "Usuário ou senha inválidos."},
            status=401,
        )

    login(request, user)

    return JsonResponse({
        "user": CurrentUserSerializer(user).data,
        "csrfToken": get_token(request),
    })


@never_cache
@require_POST
@csrf_protect
def logout_view(request):
    logout(request)

    return JsonResponse({
        "detail": "Sessão encerrada.",
        "csrfToken": get_token(request),
    })