from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListCreateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.selectors import get_accessible_stores

from .models import Customer
from .serializers import CustomerSerializer


class MyCustomersView(ListCreateAPIView):
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated]

    def _selected_store(self):
        store_id = self.request.query_params.get("store_id")
        if not store_id:
            raise ValidationError(
                {"store_id": "Informe a unidade selecionada."}
            )

        store = get_accessible_stores(self.request.user).filter(
            pk=store_id,
        ).first()
        if store is None:
            raise ValidationError(
                {"store_id": "Você não possui acesso a esta unidade."}
            )
        return store

    def get_queryset(self):
        store = self._selected_store()
        return Customer.objects.filter(
            store=store,
            is_active=True,
        ).select_related("store")

    def perform_create(self, serializer):
        serializer.save(store=self._selected_store())

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        response.status_code = status.HTTP_201_CREATED
        return response
