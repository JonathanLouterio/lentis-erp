"""Gestão global de usuários. Função por loja não substitui permissões Django."""
import json

from django.apps import apps
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from organizations.models import Store
from .models import StoreMembership, UserAccessEvent

User = get_user_model()
BUSINESS_APPS = ("organizations", "sales", "purchases")
BUSINESS_MODELS = (
    "company", "store", "customer", "product", "stockmovement", "prescription", "supplier",
    "sale", "salepayment", "receivable", "financialaccount", "financialentry", "paymentmethod",
    "quote", "serviceorder", "cashsession", "discountauthorization", "discountpolicy",
    "purchase", "payableplan", "payableinstallment", "payablepayment",
)
MAX_ID = 9223372036854775807
EDIT_FIELDS = ("username", "first_name", "last_name", "email", "is_active")


class Conflict(APIException):
    status_code = 409
    default_detail = "O cadastro foi alterado. Reabra o usuário antes de salvar."


class SystemAdministrator(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and User.objects.filter(
            pk=request.user.pk, is_active=True, is_superuser=True).exists())


def catalog():
    return Permission.objects.filter(
        content_type__app_label__in=BUSINESS_APPS,
        content_type__model__in=BUSINESS_MODELS,
    ).select_related("content_type").order_by(
        "content_type__app_label", "content_type__model", "codename")


def permission_output(permission):
    model = apps.get_model(permission.content_type.app_label, permission.content_type.model)
    singular = str(model._meta.verbose_name) if model else permission.content_type.model
    plural = str(model._meta.verbose_name_plural) if model else permission.content_type.model
    action = permission.codename.split("_", 1)[0]
    prefix = {"add": "Cadastrar", "view": "Consultar", "change": "Editar", "delete": "Excluir / inativar"}.get(action)
    return {"id": permission.pk,
            "key": f"{permission.content_type.app_label}.{permission.codename}",
            "name": f"{prefix}: {singular}" if prefix else permission.name,
            "app": permission.content_type.app_label, "model": permission.content_type.model,
            "section": plural[:1].upper() + plural[1:]}


def snapshot(user):
    return {
        **{field: getattr(user, field) for field in EDIT_FIELDS},
        "is_staff": user.is_staff, "is_superuser": user.is_superuser,
        "permission_ids": sorted(user.user_permissions.values_list("id", flat=True)),
        "group_ids": sorted(user.groups.values_list("id", flat=True)),
        "group_permission_ids": sorted(set(Permission.objects.filter(group__user=user).values_list("id", flat=True))),
        "memberships": list(StoreMembership.objects.filter(user=user).order_by("store_id").values(
            "store_id", "role", "is_active")),
    }


def version(user, state):
    # O hash da credencial participa somente do HMAC; nunca é retornado nem auditado.
    return salted_hmac("lentis.user-management.version", json.dumps(
        {"id": user.pk, "state": state, "credential": user.password}, sort_keys=True),
        algorithm="sha256").hexdigest()


def serialize(user):
    state = snapshot(user)
    allowed = set(catalog().values_list("id", flat=True))
    return {
        "id": user.pk, **{field: state[field] for field in (*EDIT_FIELDS, "is_staff", "is_superuser")},
        "version": version(user, state), "protected": user.is_superuser,
        "permission_ids": [pk for pk in state["permission_ids"] if pk in allowed],
        "inherited_permission_ids": [pk for pk in state["group_permission_ids"] if pk in allowed],
        "groups": list(user.groups.order_by("name").values_list("name", flat=True)),
        "memberships": state["memberships"],
    }


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise ValidationError({"detail": "O pedido contém campos não permitidos."})
        return super().to_internal_value(data)


class MembershipInput(StrictSerializer):
    store_id = serializers.IntegerField(min_value=1, max_value=MAX_ID)
    role = serializers.ChoiceField(choices=StoreMembership.Role.choices)
    is_active = serializers.BooleanField()


class UserInput(StrictSerializer):
    username = serializers.CharField(max_length=150, validators=User._meta.get_field("username").validators)
    first_name = serializers.CharField(max_length=150, allow_blank=True)
    last_name = serializers.CharField(max_length=150, allow_blank=True)
    email = serializers.EmailField(allow_blank=True)
    is_active = serializers.BooleanField()
    permission_ids = serializers.ListField(child=serializers.IntegerField(min_value=1, max_value=MAX_ID), max_length=2000)
    memberships = MembershipInput(many=True, max_length=500)
    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False, max_length=256)
    version = serializers.CharField(required=False, max_length=64)

    def validate(self, data):
        if len({m["store_id"] for m in data["memberships"]}) != len(data["memberships"]):
            raise ValidationError("Informe cada unidade apenas uma vez.")
        ids = set(data["permission_ids"])
        if ids != set(catalog().filter(pk__in=ids).values_list("pk", flat=True)):
            raise ValidationError("Uma das permissões não pode ser atribuída por esta tela.")
        return data


class PasswordInput(StrictSerializer):
    password = serializers.CharField(trim_whitespace=False, min_length=8, max_length=256)
    version = serializers.CharField(max_length=64)


def validate_password(password, user):
    if len(password) < 8:
        raise ValidationError({"password": ["Use pelo menos 8 caracteres."]})
    try:
        password_validation.validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise ValidationError({"password": exc.messages}) from exc


def lock_actor(request):
    # Ordem comum entre administradores para as operações desta API.
    # Evita também criações simultâneas de logins que diferem apenas na capitalização.
    list(User.objects.select_for_update().filter(is_superuser=True).order_by("pk").values_list("pk", flat=True))
    actor = User.objects.select_for_update().get(pk=request.user.pk)
    if not actor.is_active or not actor.is_superuser:
        raise PermissionDenied("Somente administradores do sistema podem gerenciar usuários.")
    return actor


def check_version(user, supplied):
    if not supplied or not constant_time_compare(supplied, version(user, snapshot(user))):
        raise Conflict()


def record_event(user, actor, action, before):
    changes = {name: {"before": before.get(name), "after": value}
               for name, value in snapshot(user).items() if before.get(name) != value}
    UserAccessEvent.objects.create(user=user, actor=actor, action=action, changes=changes)


def apply(user, data):
    if User.objects.filter(username__iexact=data["username"]).exclude(pk=user.pk).exists():
        raise ValidationError({"username": ["Já existe um usuário com este nome."]})
    stores = {s.pk: s for s in Store.objects.select_related("company").filter(
        pk__in=[m["store_id"] for m in data["memberships"]])}
    previous = {m.store_id: m for m in StoreMembership.objects.filter(user=user)} if user.pk else {}
    for member in data["memberships"]:
        store = stores.get(member["store_id"])
        if store is None:
            raise ValidationError("Unidade inexistente.")
        if member["is_active"] and (not store.is_active or not store.company.is_active):
            old = previous.get(store.pk)
            if not old or not old.is_active or old.role != member["role"]:
                raise ValidationError("Não é possível conceder acesso a uma unidade inativa.")
    for field in EDIT_FIELDS:
        setattr(user, field, data[field])
    try:
        user.full_clean(exclude=["password"])
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    user.save()
    # Não retirar concessões externas que esta interface não edita.
    external = user.user_permissions.exclude(pk__in=catalog().values_list("pk", flat=True))
    user.user_permissions.set(list(external) + list(catalog().filter(pk__in=data["permission_ids"])))
    included = []
    for member in data["memberships"]:
        StoreMembership.objects.update_or_create(user=user, store_id=member["store_id"], defaults={
            "role": member["role"], "is_active": member["is_active"]})
        included.append(member["store_id"])
    StoreMembership.objects.filter(user=user).exclude(store_id__in=included).update(is_active=False)


@method_decorator(never_cache, name="dispatch")
class AdminView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [SystemAdministrator]


class UserManagementOptionsView(AdminView):
    def get(self, request):
        return Response({
            "roles": [{"value": value, "label": label} for value, label in StoreMembership.Role.choices],
            "stores": [{"id": s.pk, "code": s.code, "name": s.name,
                        "is_active": s.is_active and s.company.is_active}
                       for s in Store.objects.select_related("company").order_by("code")],
            "permissions": [permission_output(p) for p in catalog()],
        })


class ManagedUsersView(AdminView):
    def get(self, request):
        try:
            page = int(request.query_params.get("page", "1"))
        except (ValueError, TypeError):
            raise ValidationError("Página inválida.")
        if not 1 <= page <= 100000:
            raise ValidationError("Página inválida.")
        qs = User.objects.order_by("username", "pk")
        search = request.query_params.get("search", "").strip()[:150]
        if search:
            qs = qs.filter(Q(username__icontains=search) | Q(first_name__icontains=search) | Q(last_name__icontains=search))
        count = qs.count()
        rows = [{"id": u.pk, "username": u.username, "first_name": u.first_name,
                 "last_name": u.last_name, "is_active": u.is_active, "protected": u.is_superuser}
                for u in qs[(page - 1) * 25:page * 25]]
        return Response({"results": rows, "count": count, "page": page, "has_next": page * 25 < count})

    def post(self, request):
        form = UserInput(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data
        if "version" in data or not data.get("password"):
            raise ValidationError("Informe uma senha inicial; a criação não recebe versão.")
        try:
            with transaction.atomic():
                actor = lock_actor(request)
                user = User(is_staff=False, is_superuser=False)
                for field in ("username", "first_name", "last_name", "email"):
                    setattr(user, field, data[field])
                validate_password(data["password"], user)
                user.set_password(data["password"])
                apply(user, data)
                record_event(user, actor, "created", {})
                return Response(serialize(user), status=status.HTTP_201_CREATED)
        except IntegrityError as exc:
            raise ValidationError("Não foi possível salvar. Confira o login e reabra a lista.") from exc


class ManagedUserView(AdminView):
    def get(self, request, pk):
        return Response(serialize(get_object_or_404(User, pk=pk)))

    def patch(self, request, pk):
        form = UserInput(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data
        if "password" in data:
            raise ValidationError("Use a ação específica para redefinir a senha.")
        try:
            with transaction.atomic():
                actor = lock_actor(request)
                user = get_object_or_404(User.objects.select_for_update(), pk=pk)
                if user.is_superuser:
                    raise PermissionDenied("Contas de administrador do sistema são protegidas nesta tela.")
                check_version(user, data.get("version"))
                before = snapshot(user)
                apply(user, data)
                record_event(user, actor, "updated", before)
                return Response(serialize(user))
        except IntegrityError as exc:
            raise ValidationError("Não foi possível salvar. Confira o login e reabra a lista.") from exc


class ManagedUserPasswordView(AdminView):
    def post(self, request, pk):
        form = PasswordInput(data=request.data)
        form.is_valid(raise_exception=True)
        with transaction.atomic():
            actor = lock_actor(request)
            user = get_object_or_404(User.objects.select_for_update(), pk=pk)
            if user.is_superuser:
                raise PermissionDenied("Contas de administrador do sistema são protegidas nesta tela.")
            check_version(user, form.validated_data["version"])
            password = form.validated_data["password"]
            validate_password(password, user)
            user.set_password(password)
            user.save(update_fields=["password"])
            UserAccessEvent.objects.create(user=user, actor=actor, action="password_reset", changes={})
            return Response(serialize(user))


class ManagedUserHistoryView(AdminView):
    def get(self, request, pk):
        get_object_or_404(User, pk=pk)
        return Response({"results": [{"id": e.pk, "actor": e.actor.username, "action": e.action,
                    "changes": e.changes, "created_at": e.created_at}
                for e in UserAccessEvent.objects.filter(user_id=pk).select_related("actor")[:50]]})
