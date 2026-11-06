from decimal import Decimal

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .access_permissions import FreshActiveUser, fresh_actor
from .models import Product
from .stock_transfer_models import StockTransfer
from .stock_transfer_services import (
    dispatch_transfer, eligible_destinations, for_store, product_key, resolve_transfer, transfer_capabilities,
)
from .views import SelectedStoreMixin

MAX_ID = 2**63 - 1
MAX_ITEMS = 30


class TransferLineInput(serializers.Serializer):
    source_product_id = serializers.IntegerField(min_value=1, max_value=MAX_ID)
    destination_product_id = serializers.IntegerField(min_value=1, max_value=MAX_ID)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"))


class DispatchInput(serializers.Serializer):
    destination_id = serializers.IntegerField(min_value=1, max_value=MAX_ID)
    request_id = serializers.UUIDField()
    note = serializers.CharField(max_length=255, allow_blank=True, default="")
    items = TransferLineInput(many=True, allow_empty=False, max_length=MAX_ITEMS)

    def validate_items(self, items):
        if any(len({item[field] for item in items}) != len(items)
               for field in ("source_product_id", "destination_product_id")):
            raise serializers.ValidationError("Cada produto pode aparecer somente uma vez na transferência.")
        return items


class ResolveInput(serializers.Serializer):
    action = serializers.ChoiceField(choices=("receive", "return"))
    request_id = serializers.UUIDField()
    note = serializers.CharField(max_length=255, allow_blank=True, default="")


class TransferPagination(PageNumberPagination):
    page_size = 20


@method_decorator(never_cache, name="dispatch")
class TransferBase(SelectedStoreMixin, APIView):
    permission_classes = [IsAuthenticated, FreshActiveUser]
    http_method_names = ["get", "post", "head", "options"]

    def context(self, action):
        actor = fresh_actor(self.request)
        capabilities = transfer_capabilities(actor)
        if not capabilities[action]:
            raise PermissionDenied("Seu usuário não tem permissão para esta ação de transferência.")
        return self._selected_store(), actor, capabilities

    def queryset(self, store):
        return StockTransfer.objects.filter(for_store(store.pk)).select_related(
            "source", "destination", "sent_by", "resolved_by",
        ).prefetch_related("items")

    @staticmethod
    def output(transfer, store, capabilities):
        pending = transfer.status == StockTransfer.Status.IN_TRANSIT
        return {
            "id": transfer.pk, "status": transfer.status, "status_label": transfer.get_status_display(),
            "source": {"id": transfer.source_id, "name": transfer.source.name},
            "destination": {"id": transfer.destination_id, "name": transfer.destination.name},
            "sent_by": transfer.sent_by.username, "sent_at": transfer.sent_at, "note": transfer.note,
            "resolved_by": transfer.resolved_by.username if transfer.resolved_by else None,
            "resolved_at": transfer.resolved_at, "resolution_note": transfer.resolution_note,
            "can_receive": pending and store.pk == transfer.destination_id and capabilities["receive"],
            "can_return": pending and store.pk == transfer.source_id and capabilities["return"],
            "items": [{
                "id": item.pk, "source_label": item.source_label, "destination_label": item.destination_label,
                "quantity": str(item.quantity), "outgoing_movement_id": item.outgoing_movement_id,
                "incoming_movement_id": item.incoming_movement_id,
            } for item in transfer.items.all()],
        }

    def perform(self, handler, **kwargs):
        try:
            return handler(**kwargs)
        except DjangoPermissionDenied as exc:
            raise PermissionDenied(str(exc)) from exc
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages) from exc
        except IntegrityError:
            return None

    @staticmethod
    def conflict():
        return Response(
            {"detail": "A operação conflitou com outro envio. Atualize a lista antes de tentar novamente."},
            status=status.HTTP_409_CONFLICT,
        )


class StockTransfersView(TransferBase):
    def get(self, request):
        store, _, capabilities = self.context("view")
        queryset = self.queryset(store)
        direction = request.query_params.get("direction")
        if direction == "outgoing":
            queryset = queryset.filter(source=store)
        elif direction == "incoming":
            queryset = queryset.filter(destination=store)
        elif direction not in (None, "all"):
            raise ValidationError("Direção inválida.")
        selected_status = request.query_params.get("status")
        if selected_status in StockTransfer.Status.values:
            queryset = queryset.filter(status=selected_status)
        elif selected_status not in (None, "all"):
            raise ValidationError("Situação inválida.")
        pagination = TransferPagination()
        page = pagination.paginate_queryset(queryset, request)
        return pagination.get_paginated_response([self.output(item, store, capabilities) for item in page])

    def post(self, request):
        store, actor, capabilities = self.context("add")
        data = DispatchInput(data=request.data)
        data.is_valid(raise_exception=True)
        transfer = self.perform(dispatch_transfer, user=actor, source=store, **data.validated_data)
        if transfer is None:
            return self.conflict()
        return Response(self.output(self.queryset(store).get(pk=transfer.pk), store, capabilities), status=201)


class StockTransferDetailView(TransferBase):
    def get(self, request, transfer_id):
        store, _, capabilities = self.context("view")
        return Response(self.output(get_object_or_404(self.queryset(store), pk=transfer_id), store, capabilities))

    def post(self, request, transfer_id):
        data = ResolveInput(data=request.data)
        data.is_valid(raise_exception=True)
        store, actor, capabilities = self.context(data.validated_data["action"])
        get_object_or_404(self.queryset(store), pk=transfer_id)
        transfer = self.perform(resolve_transfer, user=actor, store=store, transfer_id=transfer_id, **data.validated_data)
        if transfer is None:
            return self.conflict()
        return Response(self.output(self.queryset(store).get(pk=transfer.pk), store, capabilities))


class StockTransferOptionsView(TransferBase):
    http_method_names = ["get", "head", "options"]

    def get(self, request):
        store, actor, _ = self.context("add")
        destinations = eligible_destinations(actor, store)
        destination_id = request.query_params.get("destination_id")
        if destination_id is None:
            return Response({"destinations": list(destinations.values("id", "name")), "products": []})
        field = serializers.IntegerField(min_value=1, max_value=MAX_ID)
        destination = destinations.filter(pk=field.run_validation(destination_id)).first()
        if destination is None:
            raise ValidationError("Selecione outra unidade ativa da mesma empresa à qual você tenha acesso.")
        fields = ("id", "store_id", "barcode", "internal_code", "name", "stock_quantity")
        targets = {product_key(p): p for p in Product.objects.filter(store=destination, is_active=True).only(*fields)}
        products = []
        for origin in Product.objects.filter(store=store, is_active=True, stock_quantity__gt=0).only(*fields).order_by("name", "pk"):
            target = targets.get(product_key(origin))
            if target:
                products.append({
                    "source_product_id": origin.pk, "destination_product_id": target.pk,
                    "source_label": str(origin), "destination_label": str(target), "source_stock": str(origin.stock_quantity),
                })
        return Response({"destinations": [], "products": products})
