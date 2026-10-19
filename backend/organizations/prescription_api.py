import hashlib
import json
from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from accounts.selectors import get_accessible_stores
from .models import Customer, Prescription, PrescriptionRevision, PrescriptionOperation
from .prescription_models import CLINICAL_FIELDS
from .views import SelectedStoreMixin


def require_permission(user, action):
    permission = 'add' if action == 'created' else 'change'
    if not user.is_active or not user.has_perm('organizations.view_prescription'):
        raise PermissionDenied('Seu usuário precisa da permissão de visualizar receitas oftalmológicas.')
    if action and not user.has_perm(f'organizations.{permission}_prescription'):
        raise PermissionDenied('Seu usuário não tem permissão para registrar ou corrigir receitas.')


def snapshot(record):
    result = {field: getattr(record, field) for field in CLINICAL_FIELDS}
    return {**{key: str(value) if isinstance(value,(date,Decimal)) else value for key,value in result.items()}, 'customer_id':record.customer_id, 'is_active':record.is_active}


class PrescriptionInput(serializers.ModelSerializer):
    request_id = serializers.UUIDField()
    expected_version = serializers.IntegerField(min_value=1, max_value=2147483647, required=False)
    reason = serializers.CharField(max_length=255, allow_blank=True, default='')
    customer_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807)
    class Meta:
        model = Prescription
        fields = ['request_id','expected_version','reason','customer_id',*CLINICAL_FIELDS]
    def validate_customer_id(self, value):
        customer = Customer.objects.filter(pk=value, store=self.context['store'], is_active=True).first()
        if customer is None: raise serializers.ValidationError('Selecione um cliente ativo desta unidade.')
        return customer


class ArchiveInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    expected_version = serializers.IntegerField(min_value=1, max_value=2147483647)
    reason = serializers.CharField(max_length=255, allow_blank=False)


class PrescriptionOutput(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name')
    creator_username = serializers.CharField(source='created_by.username')
    editor_username = serializers.CharField(source='updated_by.username')
    class Meta:
        model = Prescription
        fields = ['id','store','customer','customer_name',*CLINICAL_FIELDS,'version','is_active','creator_username','editor_username','created_at','updated_at']


def query(store):
    return Prescription.objects.filter(store=store).select_related('customer','created_by','updated_by')


def operate(request, store, action, record_id=None):
    user = request.user
    require_permission(user, action)
    if not isinstance(request.data,dict): raise ValidationError('Envie os campos da receita em JSON.')
    identity = serializers.UUIDField().run_validation(request.data.get('request_id'))
    digest = hashlib.sha256(json.dumps({'action':action,'id':record_id,'data':request.data}, sort_keys=True, separators=(',',':')).encode()).hexdigest()
    try:
        with transaction.atomic():
            user = get_user_model().objects.select_for_update(no_key=True).get(pk=user.pk)
            require_permission(user,action)
            if not get_accessible_stores(user).filter(pk=store.pk).exists(): raise PermissionDenied('O acesso à unidade foi retirado.')
            old = PrescriptionOperation.objects.select_related('prescription').filter(request_id=identity).first()
            if old:
                if old.created_by_id != user.pk or old.prescription.store_id != store.pk: raise PermissionDenied('Operação de outra conta ou unidade.')
                if old.digest != digest: raise ValidationError('Identificador já usado com outros dados.')
                return old.prescription
            record = get_object_or_404(Prescription.objects.select_for_update(of=('self',)), pk=record_id, store=store) if record_id else None
            serializer = (ArchiveInput if action=='archived' else PrescriptionInput)(data=request.data, context={'store':store})
            serializer.is_valid(raise_exception=True)
            values = dict(serializer.validated_data); values.pop('request_id')
            expected = values.pop('expected_version',None); reason = values.pop('reason','').strip()
            if record:
                if not record.is_active: raise ValidationError('Esta receita está arquivada e seu histórico deve ser preservado.')
                if expected != record.version: raise ValidationError('A receita foi atualizada. Reabra os dados atuais antes de corrigir.')
                if not reason: raise ValidationError({'reason':'Informe o motivo da correção ou do arquivamento.'})
                record.version += 1
            if action == 'archived': record.is_active = False
            else:
                customer = values.pop('customer_id')
                if record and record.customer_id != customer.pk: raise ValidationError('Não é permitido transferir uma receita para outro cliente.')
                if record is None: record = Prescription(store=store, customer=customer, created_by=user, updated_by=user)
                for field in CLINICAL_FIELDS:
                    setattr(record, field, values.get(field, None if field in ['od_axis','oe_axis','od_sphere','oe_sphere','od_cylinder','oe_cylinder','od_addition','oe_addition','pd','od_dnp','oe_dnp'] else ''))
            record.updated_by = user
            record.save(_service=True)
            PrescriptionRevision.objects.create(prescription=record,version=record.version,action=action,reason=reason or 'Cadastro inicial',snapshot=snapshot(record),created_by=user)
            PrescriptionOperation.objects.create(request_id=identity,prescription=record,digest=digest,created_by=user)
            return record
    except ModelValidationError as exc:
        raise ValidationError(exc.message_dict if hasattr(exc,'message_dict') else exc.messages) from exc


class PrescriptionBase(SelectedStoreMixin, APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    def output(self, record): return Response(PrescriptionOutput(query(record.store).get(pk=record.pk)).data)
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request,response,*args,**kwargs)
        response['Cache-Control'] = 'no-store, private'
        return response


class PrescriptionsView(PrescriptionBase):
    def get(self, request):
        store = self._selected_store(); require_permission(request.user,None)
        records = query(store)
        state = request.query_params.get('status','active')
        if state in ('active','archived'): records=records.filter(is_active=state=='active')
        elif state!='all': raise ValidationError('Selecione uma situação válida.')
        customer_id = request.query_params.get('customer_id')
        if customer_id:
            customer_id = serializers.IntegerField(min_value=1,max_value=9223372036854775807).run_validation(customer_id)
            records=records.filter(customer_id=customer_id)
        pagination = PageNumberPagination(); pagination.page_size=25
        rows=pagination.paginate_queryset(records,request,view=self)
        response = pagination.get_paginated_response(PrescriptionOutput(rows,many=True).data)
        response.data['can_create']=request.user.has_perm('organizations.add_prescription')
        response.data['can_edit']=request.user.has_perm('organizations.change_prescription')
        return response
    def post(self,request): return self.output(operate(request,self._selected_store(),'created'))


class PrescriptionDetailView(PrescriptionBase):
    def get(self,request,record_id):
        store=self._selected_store(); require_permission(request.user,None)
        record=get_object_or_404(query(store),pk=record_id)
        result=PrescriptionOutput(record).data
        result['revisions']=[{'version':r.version,'action':r.action,'reason':r.reason,'created_at':r.created_at,'creator_username':r.created_by.username,'snapshot':r.snapshot} for r in record.revisions.select_related('created_by')]
        return Response(result)
    def put(self,request,record_id): return self.output(operate(request,self._selected_store(),'updated',record_id))


class PrescriptionArchiveView(PrescriptionBase):
    def post(self,request,record_id): return self.output(operate(request,self._selected_store(),'archived',record_id))
