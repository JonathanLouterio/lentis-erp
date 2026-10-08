from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.selectors import get_accessible_stores

from .models import Customer, Product, StockMovement
from .serializers import (
    CustomerSerializer, ProductSerializer,
    StockMovementCreateSerializer, StockMovementSerializer,
)
from .stock_services import register_stock_movement


class SelectedStoreMixin:
    def _selected_store(self):
        store_id = self.request.query_params.get("store_id")
        if not store_id:
            raise ValidationError({"store_id": "Informe a unidade selecionada."})
        try:
            store_id = int(store_id)
        except (TypeError, ValueError) as exc:
            raise ValidationError({"store_id": "Informe um código de unidade válido."}) from exc
        if not 0 < store_id <= 9223372036854775807:
            raise ValidationError({"store_id": "Informe um código de unidade válido."})
        store = get_accessible_stores(self.request.user).filter(pk=store_id).first()
        if store is None:
            raise ValidationError({"store_id": "Você não possui acesso a esta unidade."})
        return store


class MyCustomersView(SelectedStoreMixin, ListCreateAPIView):
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Customer.objects.filter(store=self._selected_store(), is_active=True).select_related("store")

    def perform_create(self, serializer):
        serializer.save(store=self._selected_store())


class MyCustomerDetailView(SelectedStoreMixin, RetrieveUpdateDestroyAPIView):
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "customer_id"

    def get_queryset(self):
        return Customer.objects.filter(store=self._selected_store(), is_active=True).select_related("store")

    def destroy(self, request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            raise PermissionDenied("Somente administradores podem excluir clientes.")
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class MyProductsView(SelectedStoreMixin, ListCreateAPIView):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Product.objects.filter(store=self._selected_store(), is_active=True).select_related("store")

    def perform_create(self, serializer):
        serializer.save(store=self._selected_store())


class MyProductDetailView(SelectedStoreMixin, RetrieveUpdateDestroyAPIView):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "product_id"

    def get_queryset(self):
        return Product.objects.filter(store=self._selected_store(), is_active=True).select_related("store")

    def destroy(self, request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            raise PermissionDenied("Somente administradores podem inativar produtos.")
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class MyStockMovementsView(SelectedStoreMixin, ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return StockMovementCreateSerializer
        return StockMovementSerializer

    def get_queryset(self):
        queryset = StockMovement.objects.filter(store=self._selected_store()).select_related(
            "store", "product", "created_by",
        )
        product_id = self.request.query_params.get("product_id")
        if product_id is not None:
            try:
                product_id = int(product_id)
            except (TypeError, ValueError) as exc:
                raise ValidationError({"product_id": "Informe um código de produto válido."}) from exc
            if not 0 < product_id <= 9223372036854775807:
                raise ValidationError({"product_id": "Informe um código de produto válido."})
            queryset = queryset.filter(product_id=product_id)
        return queryset

    def create(self, request, *args, **kwargs):
        store = self._selected_store()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            movement = register_stock_movement(
                user=request.user, store_id=store.pk, **serializer.validated_data,
            )
        except DjangoPermissionDenied as exc:
            raise PermissionDenied(str(exc)) from exc
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else exc.messages
            raise ValidationError(detail) from exc
        output = StockMovementSerializer(movement, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)
