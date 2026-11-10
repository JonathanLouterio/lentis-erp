"""Modelos da unidade: preencher uma despesa é uma operação separada."""
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.response import Response

from sales.views import SalesPagination, model_errors
from .access_permissions import payable_capabilities
from .models import ExpenseTemplate, PayablePlan
from .payable_services import actor
from .payable_views import PayablesView


class TemplateConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'O modelo foi alterado. Reabra os dados antes de salvar.'


class TemplateInput(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    category = serializers.ChoiceField(choices=PayablePlan.ExpenseCategory.choices)
    description = serializers.CharField(max_length=160)
    payee = serializers.CharField(max_length=140, required=False, allow_blank=True, default='')
    suggested_amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal('0.01'), allow_null=True)
    due_day = serializers.IntegerField(min_value=1, max_value=31, allow_null=True)


class TemplateUpdate(TemplateInput):
    active = serializers.BooleanField()
    version = serializers.IntegerField(min_value=1, max_value=2147483647)


class TemplateOutput(serializers.ModelSerializer):
    category_label = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = ExpenseTemplate
        fields = ['id', 'name', 'category', 'category_label', 'description', 'payee', 'suggested_amount', 'due_day', 'active', 'version']


class ExpenseTemplatesView(PayablesView):
    payable_action = 'manage_templates'

    def get(self, request):
        store = self.check_access()
        caps = payable_capabilities(request.user)
        if not (caps['expense'] or caps['manage_templates']):
            raise PermissionDenied('Seu usuário não tem permissão para consultar modelos de despesas.')
        state = request.query_params.get('status', 'active')
        if state not in ('active', 'all'):
            raise ValidationError('Situação de modelo inválida.')
        if state == 'all' and not caps['manage_templates']:
            raise PermissionDenied('Somente quem gerencia modelos pode consultar os arquivados.')
        search = request.query_params.get('search', '').strip()
        if len(search) > 100:
            raise ValidationError('Informe até 100 caracteres para buscar um modelo.')
        rows = ExpenseTemplate.objects.filter(store=store).order_by(Lower('name'), 'pk')
        if state == 'active':
            rows = rows.filter(active=True)
        if search:
            rows = rows.filter(Q(name__icontains=search) | Q(description__icontains=search))
        pager = SalesPagination()
        page = pager.paginate_queryset(rows, request, view=self)
        return pager.get_paginated_response(TemplateOutput(page, many=True).data)

    def write_template(self, request, template_id=None):
        store = self.check_access()
        values = dict(self.write_serializer(TemplateInput if template_id is None else TemplateUpdate, request.data, store).validated_data)
        try:
            with transaction.atomic(), model_errors():
                user = actor(request.user, store, 'manage_expense_templates')
                if template_id is None:
                    model = ExpenseTemplate(store=store, created_by=user)
                else:
                    model = get_object_or_404(ExpenseTemplate.objects.select_for_update(), pk=template_id, store=store)
                    if values.pop('version') != model.version:
                        raise TemplateConflict()
                    model.version += 1
                for name, value in values.items():
                    setattr(model, name, value)
                model.updated_by = user
                model.save()
        except IntegrityError as exc:
            raise ValidationError({'name': 'Já existe um modelo com esse nome nesta unidade, inclusive entre os arquivados.'}) from exc
        return Response(TemplateOutput(model).data, status=status.HTTP_201_CREATED if template_id is None else status.HTTP_200_OK)

    def post(self, request):
        return self.write_template(request)


class ExpenseTemplateDetailView(ExpenseTemplatesView):
    http_method_names = ['post', 'options']

    def post(self, request, template_id):
        return self.write_template(request, template_id)
