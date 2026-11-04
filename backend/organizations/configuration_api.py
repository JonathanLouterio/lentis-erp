"""Configurações globais: sessão, CSRF, administrador atual e alterações auditadas."""
import hashlib
import json
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.user_management_api import SystemAdministrator, StrictSerializer
from .models import Company, Store, ConfigurationEvent

COMPANY_FIELDS = ('name', 'legal_name', 'email', 'phone', 'address', 'city', 'state',
                  'website', 'instagram', 'facebook', 'tiktok', 'whatsapp', 'is_active')
STORE_FIELDS = ('code', 'name', 'email', 'phone', 'address', 'city', 'state',
                'allow_negative_stock', 'is_active')
STATES = set('AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split())
MAX_ID = 9223372036854775807


class ConfigurationConflict(APIException):
    status_code = 409
    default_detail = 'Este cadastro mudou. Feche e reabra o formulário antes de salvar.'


class CompanyOutput(serializers.ModelSerializer):
    version = serializers.IntegerField(source='configuration_version', read_only=True)

    class Meta:
        model = Company
        fields = ('id', *COMPANY_FIELDS, 'version', 'updated_at')


class StoreOutput(serializers.ModelSerializer):
    version = serializers.IntegerField(source='configuration_version', read_only=True)
    company_id = serializers.IntegerField(read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True)
    company_active = serializers.BooleanField(source='company.is_active', read_only=True)

    class Meta:
        model = Store
        fields = ('id', 'company_id', 'company_name', 'company_active', *STORE_FIELDS, 'version', 'updated_at')


class ContactInput(StrictSerializer):
    request_id = serializers.UUIDField()
    version = serializers.IntegerField(min_value=1, required=False)
    name = serializers.CharField(max_length=150, required=False)
    email = serializers.EmailField(max_length=254, allow_blank=True, required=False)
    phone = serializers.CharField(max_length=30, allow_blank=True, required=False)
    address = serializers.CharField(max_length=250, allow_blank=True, required=False)
    city = serializers.CharField(max_length=100, allow_blank=True, required=False)
    state = serializers.CharField(max_length=2, allow_blank=True, required=False)
    is_active = serializers.BooleanField(required=False)

    def validate_state(self, value):
        value = value.upper()
        if value and value not in STATES:
            raise ValidationError('Informe uma UF brasileira válida.')
        return value


class CompanyInput(ContactInput):
    legal_name = serializers.CharField(max_length=200, allow_blank=True, required=False)
    website = serializers.URLField(max_length=300, allow_blank=True, required=False)
    instagram = serializers.URLField(max_length=300, allow_blank=True, required=False)
    facebook = serializers.URLField(max_length=300, allow_blank=True, required=False)
    tiktok = serializers.URLField(max_length=300, allow_blank=True, required=False)
    whatsapp = serializers.CharField(max_length=20, allow_blank=True, required=False)

    def validate(self, data):
        for field in ('website', 'instagram', 'facebook', 'tiktok'):
            if data.get(field):
                url = urlsplit(data[field])
                if url.scheme != 'https' or url.username or url.password:
                    raise ValidationError({field: 'Informe um link HTTPS sem credenciais.'})
        if data.get('whatsapp'):
            value = data['whatsapp']
            if any(c not in '+0123456789 ()-' for c in value):
                raise ValidationError({'whatsapp': 'Informe somente o telefone com DDI e DDD.'})
            digits = ''.join(c for c in value if c in '0123456789')
            if not 10 <= len(digits) <= 15:
                raise ValidationError({'whatsapp': 'Informe entre 10 e 15 dígitos, incluindo DDI e DDD.'})
            data['whatsapp'] = digits
        return data


class StoreInput(ContactInput):
    company_id = serializers.IntegerField(min_value=1, max_value=MAX_ID, required=False)
    code = serializers.RegexField(r'^[A-Za-z0-9_-]+$', max_length=10, required=False,
                                 error_messages={'invalid': 'Use letras, números, hífen ou sublinhado no código.'})
    allow_negative_stock = serializers.BooleanField(required=False)

    def validate_code(self, value):
        return value.upper()


class ListingInput(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, max_value=1000000, default=1)
    company_id = serializers.IntegerField(min_value=1, max_value=MAX_ID, required=False)
    q = serializers.CharField(max_length=150, allow_blank=True, default='')


def page_result(queryset, page, serialize):
    count = queryset.count()
    start = (page - 1) * 25
    return {'count': count, 'has_next': start + 25 < count,
            'results': [serialize(obj) for obj in queryset[start:start + 25]]}


@method_decorator(never_cache, name='dispatch')
class ConfigurationView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [SystemAdministrator]

    def query(self, request):
        serializer = ListingInput(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def write(self, request, kind, pk=None):
        input_type, output_type, model, fields = (
            (CompanyInput, CompanyOutput, Company, COMPANY_FIELDS) if kind == 'company' else
            (StoreInput, StoreOutput, Store, STORE_FIELDS))
        payload = input_type(data=request.data)
        payload.is_valid(raise_exception=True)
        data = dict(payload.validated_data)
        request_id = data.pop('request_id')
        fingerprint = hashlib.sha256(json.dumps(
            [kind, pk, data], sort_keys=True, default=str).encode()).hexdigest()
        supplied_version = data.pop('version', None)
        try:
            with transaction.atomic():
                # Serializa reenvios do mesmo ator e revalida revogação de privilégio.
                actor = get_user_model().objects.select_for_update().filter(
                    pk=request.user.pk, is_active=True, is_superuser=True).first()
                if not actor:
                    raise PermissionDenied('Acesso administrativo revogado.')
                old_event = ConfigurationEvent.objects.filter(request_id=request_id).first()
                if old_event:
                    if old_event.actor_id != actor.pk or old_event.fingerprint != fingerprint:
                        raise ConfigurationConflict('Identificador de envio reutilizado com outros dados. Reabra o formulário.')
                    return Response(old_event.result, status=201 if pk is None else 200)
                obj = get_object_or_404(model.objects.select_for_update(), pk=pk) if pk else model()
                if pk and supplied_version != obj.configuration_version:
                    raise ConfigurationConflict()
                if not pk:
                    required = ['name'] + (['code', 'company_id'] if kind == 'store' else [])
                    missing = [field for field in required if not data.get(field)]
                    if missing:
                        raise ValidationError({field: 'Campo obrigatório.' for field in missing})
                if kind == 'store':
                    company_id = data.pop('company_id', obj.company_id)
                    if pk and company_id != obj.company_id:
                        raise ValidationError({'company_id': 'A empresa da unidade não pode ser alterada.'})
                    company = get_object_or_404(Company.objects.select_for_update(), pk=company_id)
                    if (not pk or (data.get('is_active') is True and not obj.is_active)) and not company.is_active:
                        raise ValidationError({'company_id': 'Ative a empresa antes de criar ou reativar uma unidade.'})
                    obj.company = company
                before = {field: getattr(obj, field) for field in fields} if pk else {}
                for field, value in data.items():
                    setattr(obj, field, value)
                if pk:
                    obj.configuration_version += 1
                obj.full_clean()
                obj.save()
                result = dict(output_type(obj).data)
                changes = {field: {'before': before.get(field), 'after': getattr(obj, field)}
                           for field in fields if not pk or before[field] != getattr(obj, field)}
                ConfigurationEvent.objects.create(
                    company=obj if kind == 'company' else obj.company,
                    store=obj if kind == 'store' else None, actor=actor,
                    action=f'{kind}_{"updated" if pk else "created"}', changes=changes,
                    request_id=request_id, fingerprint=fingerprint, result=result)
                return Response(result, status=200 if pk else 201)
        except ModelValidationError as exc:
            raise ValidationError(exc.message_dict if hasattr(exc, 'message_dict') else exc.messages) from exc
        except IntegrityError as exc:
            raise ConfigurationConflict('Conflito ao salvar. Atualize a lista e confira o código da unidade.') from exc


class CompaniesView(ConfigurationView):
    def get(self, request):
        query = self.query(request)
        qs = Company.objects.order_by('name', 'pk')
        if query['q']:
            qs = qs.filter(Q(name__icontains=query['q']) | Q(legal_name__icontains=query['q']))
        return Response(page_result(qs, query['page'], lambda obj: CompanyOutput(obj).data))

    def post(self, request):
        return self.write(request, 'company')


class CompanyDetailView(ConfigurationView):
    def get(self, request, pk):
        return Response(CompanyOutput(get_object_or_404(Company, pk=pk)).data)

    def patch(self, request, pk):
        return self.write(request, 'company', pk)


class ConfigurationStoresView(ConfigurationView):
    def get(self, request):
        query = self.query(request)
        if 'company_id' not in query:
            raise ValidationError({'company_id': 'Selecione uma empresa.'})
        get_object_or_404(Company, pk=query['company_id'])
        qs = Store.objects.select_related('company').filter(company_id=query['company_id']).order_by('code', 'pk')
        if query['q']:
            qs = qs.filter(Q(name__icontains=query['q']) | Q(code__icontains=query['q']))
        return Response(page_result(qs, query['page'], lambda obj: StoreOutput(obj).data))

    def post(self, request):
        return self.write(request, 'store')


class ConfigurationStoreDetailView(ConfigurationView):
    def get(self, request, pk):
        return Response(StoreOutput(get_object_or_404(Store.objects.select_related('company'), pk=pk)).data)

    def patch(self, request, pk):
        return self.write(request, 'store', pk)


class ConfigurationHistoryView(ConfigurationView):
    def get(self, request):
        query = self.query(request)
        if 'company_id' not in query:
            raise ValidationError({'company_id': 'Selecione uma empresa.'})
        get_object_or_404(Company, pk=query['company_id'])
        qs = ConfigurationEvent.objects.filter(company_id=query['company_id']).select_related('actor', 'store')
        return Response(page_result(qs, query['page'], lambda event: {
            'id': event.pk, 'action': event.action, 'actor': event.actor.username,
            'store_name': event.store.name if event.store else None,
            'changes': event.changes, 'created_at': event.created_at.isoformat(),
        }))
