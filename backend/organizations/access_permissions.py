from django.contrib.auth import get_user_model
from rest_framework.permissions import BasePermission
from rest_framework.exceptions import ValidationError


METHOD_ACTIONS = {
    "GET": "view", "HEAD": "view", "OPTIONS": "view",
    "POST": "add", "PUT": "change", "PATCH": "change", "DELETE": "delete",
}


def fresh_actor(request):
    """Permissões novas a cada requisição, inclusive com force_authenticate em testes."""
    if not hasattr(request, "_catalog_actor"):
        request._catalog_actor = None
        if request.user.is_authenticated:
            request._catalog_actor = get_user_model().objects.filter(
                pk=request.user.pk, is_active=True).first()
    return request._catalog_actor


class FreshActiveUser(BasePermission):
    message = "Entre com uma conta ativa para continuar."

    def has_permission(self, request, view):
        return fresh_actor(request) is not None


class CatalogActionPermission(BasePermission):
    message = "Seu usuário não tem permissão para esta ação. Solicite a liberação ao administrador."

    def has_permission(self, request, view):
        user = fresh_actor(request)
        if user is None:
            return False
        if request.method.lower() not in view.http_method_names:
            return True  # Preserva o 405 para métodos não implementados.
        action = METHOD_ACTIONS.get(request.method)
        model = getattr(view, "catalog_model", None)
        return bool(action and model and user.has_perm(f"organizations.{action}_{model}"))


def catalog_capabilities(user):
    result = {}
    for section, model in (("customers", "customer"), ("products", "product")):
        result[section] = {action: user.has_perm(f"organizations.{action}_{model}")
                           for action in ("view", "add", "change", "delete")}
    result["stock"] = {action: user.has_perm(f"organizations.{action}_stockmovement")
                       for action in ("view", "add")}
    return result


class CatalogWriteGuardMixin:
    def get_serializer(self, *args, **kwargs):
        data = kwargs.get("data")
        if isinstance(data, dict) and "is_active" in data:
            raise ValidationError({"is_active": "Use a ação de inativar, que exige sua permissão específica."})
        return super().get_serializer(*args, **kwargs)
