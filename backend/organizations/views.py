from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.selectors import get_accessible_stores

from .models import Customer
from .serializers import CustomerSerializer


class SelectedStoreMixin:
    def _selected_store(self):
        store_id = self.request.query_params.get("store_id")
        if not store_id:
            raise ValidationError({"store_id": "Informe a unidade selecionada."})

        store = get_accessible_stores(self.request.user).filter(pk=store_id).first()
        if store is None:
            raise ValidationError(
                {"store_id": "Você não possui acesso a esta unidade."}
            )
        return store


class MyCustomersView(SelectedStoreMixin, ListCreateAPIView):
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Customer.objects.filter(
            store=self._selected_store(),
            is_active=True,
        ).select_related("store")

    def perform_create(self, serializer):
        serializer.save(store=self._selected_store())

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        response.status_code = status.HTTP_201_CREATED
        return response


class MyCustomerDetailView(SelectedStoreMixin, RetrieveUpdateDestroyAPIView):
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "customer_id"

    def get_queryset(self):
        return Customer.objects.filter(
            store=self._selected_store(),
            is_active=True,
        ).select_related("store")

    def destroy(self, request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            raise PermissionDenied("Somente administradores podem excluir clientes.")

        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)
