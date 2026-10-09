from contextlib import contextmanager

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from organizations.views import SelectedStoreMixin

from .models import Sale, SaleItem
from .serializers import (
    SaleCancelSerializer, SaleCreateSerializer, SaleDraftSerializer,
    SaleItemWriteSerializer, SaleSerializer,
)
from .services import cancel_sale
from .payment_services import complete_sale


@contextmanager
def model_errors():
    try:
        yield
    except DjangoValidationError as exc:
        detail = exc.message_dict if hasattr(exc, "message_dict") else exc.messages
        raise ValidationError(detail) from exc
    except DjangoPermissionDenied as exc:
        raise PermissionDenied(str(exc)) from exc


def sale_queryset():
    return Sale.objects.select_related("store", "customer", "created_by").prefetch_related("items", "events__created_by", "payments__method", "payments__account", "payments__installments__entries__account", "payments__installments__entries__method", "payments__installments__entries__created_by")


class SalesPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class SalesBaseView(SelectedStoreMixin, APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def selected_sale(self, sale_id, *, lock=False):
        store = self._selected_store()
        queryset = Sale.objects.select_for_update(of=("self",)) if lock else sale_queryset()
        return get_object_or_404(queryset, pk=sale_id, store=store)

    def output(self, sale, *, response_status=status.HTTP_200_OK):
        current = sale_queryset().get(pk=sale.pk)
        data = SaleSerializer(current, context={"request": self.request}).data
        return Response(data, status=response_status)

    def require_draft(self, sale):
        if sale.status != Sale.Status.DRAFT:
            raise ValidationError("Somente vendas em rascunho podem ser editadas.")

    def write_serializer(self, serializer_class, data, store, *, partial=False):
        serializer = serializer_class(data=data, partial=partial, context={"store": store})
        serializer.is_valid(raise_exception=True)
        return serializer

    def add_item(self, sale, values):
        values = dict(values)
        product = values.pop("product_id")
        return SaleItem.objects.create(sale=sale, product=product, **values)


class MySalesView(SalesBaseView):
    def get(self, request):
        queryset = sale_queryset().filter(store=self._selected_store())
        sale_status = request.query_params.get("status")
        if sale_status is not None:
            if sale_status not in Sale.Status.values:
                raise ValidationError({"status": "Informe uma situação válida de venda."})
            queryset = queryset.filter(status=sale_status)
        pagination = SalesPagination()
        page = pagination.paginate_queryset(queryset, request, view=self)
        data = SaleSerializer(page, many=True, context={"request": request}).data
        return pagination.get_paginated_response(data)

    def post(self, request):
        store = self._selected_store()
        values = dict(self.write_serializer(SaleCreateSerializer, request.data, store).validated_data)
        items = values.pop("items", [])
        customer = values.pop("customer_id", None)
        with model_errors(), transaction.atomic():
            sale = Sale.objects.create(store=store, customer=customer, created_by=request.user, **values)
            for item in items:
                self.add_item(sale, item)
            return self.output(sale, response_status=status.HTTP_201_CREATED)


class MySaleDetailView(SalesBaseView):
    def get(self, request, sale_id):
        sale = self.selected_sale(sale_id)
        return Response(SaleSerializer(sale, context={"request": request}).data)

    def patch(self, request, sale_id):
        with model_errors(), transaction.atomic():
            sale = self.selected_sale(sale_id, lock=True)
            self.require_draft(sale)
            values = self.write_serializer(SaleDraftSerializer, request.data, sale.store, partial=True).validated_data
            if "customer_id" in values:
                sale.customer = values["customer_id"]
            if "notes" in values:
                sale.notes = values["notes"]
            sale.save()
            return self.output(sale)


class MySaleItemsView(SalesBaseView):
    def post(self, request, sale_id):
        with model_errors(), transaction.atomic():
            sale = self.selected_sale(sale_id, lock=True)
            self.require_draft(sale)
            values = self.write_serializer(SaleItemWriteSerializer, request.data, sale.store).validated_data
            self.add_item(sale, values)
            return self.output(sale, response_status=status.HTTP_201_CREATED)


class MySaleItemDetailView(SalesBaseView):
    def patch(self, request, sale_id, item_id):
        with model_errors(), transaction.atomic():
            sale = self.selected_sale(sale_id, lock=True)
            self.require_draft(sale)
            item = get_object_or_404(SaleItem, pk=item_id, sale=sale)
            values = dict(self.write_serializer(SaleItemWriteSerializer, request.data, sale.store, partial=True).validated_data)
            product = values.pop("product_id", item.product)
            if product.pk != item.product_id:
                raise ValidationError({"product_id": "Remova o item e adicione o novo produto para substituí-lo."})
            for key, value in values.items():
                setattr(item, key, value)
            item.save()
            return self.output(sale)

    def delete(self, request, sale_id, item_id):
        with model_errors(), transaction.atomic():
            sale = self.selected_sale(sale_id, lock=True)
            self.require_draft(sale)
            item = get_object_or_404(SaleItem, pk=item_id, sale=sale)
            item.delete()
            return self.output(sale)


class MySaleFinalizeView(SalesBaseView):
    def post(self, request, sale_id):
        self.selected_sale(sale_id)
        with model_errors():
            sale = complete_sale(user=request.user, sale_id=sale_id)
            return self.output(sale)


class MySaleCancelView(SalesBaseView):
    def post(self, request, sale_id):
        selected = self.selected_sale(sale_id)
        serializer = self.write_serializer(SaleCancelSerializer, request.data, selected.store)
        with model_errors():
            sale = cancel_sale(user=request.user, sale_id=sale_id, **serializer.validated_data)
            return self.output(sale)
