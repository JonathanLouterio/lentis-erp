import hashlib
import json
from django.core.exceptions import ValidationError as ModelValidationError
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from accounts.selectors import get_accessible_stores
from sales.views import SalesBaseView, SalesPagination, model_errors
from .supplier_models import Supplier, SupplierEvent, SupplierOperation, normalize_document

FIELDS=('person_type','name','trade_name','document','state_registration','contact_name','phone','whatsapp','email','zip_code','street','address_number','address_complement','neighborhood','city','state','notes')


class SupplierInput(serializers.ModelSerializer):
    request_id=serializers.UUIDField()
    expected_version=serializers.IntegerField(min_value=1,required=False)
    action=serializers.ChoiceField(choices=['create','update','archive','restore'])
    reason=serializers.CharField(max_length=255,allow_blank=True,required=False)
    class Meta:
        model=Supplier
        fields=[*FIELDS,'request_id','expected_version','action','reason']
        extra_kwargs={'name':{'required':False},'document':{'validators':[]}}
        validators=[]

    def validate(self,values):
        if values['action']=='create' and not values.get('name','').strip():raise serializers.ValidationError({'name':'Informe o nome ou razão social.'})
        if values['action']!='create' and 'expected_version' not in values:raise serializers.ValidationError('Informe a versão atual do fornecedor.')
        return values


def output(supplier,detail=False):
    result={key:getattr(supplier,key) for key in FIELDS}
    result.update(id=supplier.pk,store=supplier.store_id,is_active=supplier.is_active,version=supplier.version,created_at=supplier.created_at,updated_at=supplier.updated_at)
    if detail:
        result['events']=[{'action':e.action,'action_label':e.get_action_display(),'reason':e.reason,'version':e.version,'creator_username':e.created_by.username,'created_at':e.created_at} for e in supplier.events.select_related('created_by')]
    return result


def operate_supplier(*,user,store,supplier_id,values,digest):
    with transaction.atomic():
        user=get_user_model().objects.select_for_update(no_key=True).get(pk=user.pk)
        if not get_accessible_stores(user).filter(pk=store.pk).exists():raise PermissionDenied('O acesso à unidade não está disponível.')
        action=values['action']; permission='add' if supplier_id is None else 'change'
        if not user.has_perm('organizations.view_supplier') or not user.has_perm(f'organizations.{permission}_supplier'):raise PermissionDenied('Você não tem permissão para esta operação com fornecedores.')
        previous=SupplierOperation.objects.select_related('supplier').filter(request_id=values['request_id']).first()
        if previous:
            if previous.created_by_id!=user.pk or previous.supplier.store_id!=store.pk:raise PermissionDenied('Este envio pertence a outra conta ou unidade.')
            if previous.digest!=digest:raise ValidationError('O identificador já foi utilizado com outros dados.')
            return previous.supplier
        reason=values.get('reason','').strip()
        if supplier_id is None:
            if action!='create':raise ValidationError('Operação inválida para novo fornecedor.')
            supplier=Supplier(store=store,created_by=user,updated_by=user)
        else:
            supplier=get_object_or_404(Supplier.objects.select_for_update(),pk=supplier_id,store=store)
            if values.get('expected_version')!=supplier.version:raise ValidationError('O fornecedor foi alterado. Reabra o cadastro antes de salvar.')
            if action=='create':raise ValidationError('Use a operação de edição para este fornecedor.')
            if action in ('archive','restore'):
                if not reason:raise ValidationError('Informe o motivo da inativação ou reativação.')
                target=action=='restore'
                if supplier.is_active==target:raise ValidationError('O fornecedor já está nesta situação. Atualize a lista.')
                supplier.is_active=target
            supplier.version+=1;supplier.updated_by=user
        if action in ('create','update'):
            for key in FIELDS:
                if key in values:setattr(supplier,key,values[key])
        supplier.document=normalize_document(supplier.document)
        duplicate=Supplier.objects.filter(store=store,document=supplier.document).exclude(pk=supplier.pk)
        if supplier.document and duplicate.exists():raise ValidationError({'document':'Já existe um fornecedor com este documento nesta unidade. Confira também os inativos.'})
        supplier.save(_service=True)
        SupplierEvent.objects.create(supplier=supplier,version=supplier.version,action=action,reason=reason,created_by=user)
        SupplierOperation.objects.create(supplier=supplier,request_id=values['request_id'],digest=digest,created_by=user)
        return supplier


class SuppliersView(SalesBaseView):
    def check_access(self):
        store=self._selected_store()
        if not self.request.user.has_perm('organizations.view_supplier'):raise PermissionDenied('Seu usuário precisa da permissão de visualizar fornecedores.')
        return store

    def get(self,request):
        store=self.check_access();qs=Supplier.objects.filter(store=store)
        state=request.query_params.get('status','active')
        if state not in ('active','inactive','all'):raise ValidationError('Selecione ativos, inativos ou todos.')
        if state!='all':qs=qs.filter(is_active=state=='active')
        query=request.query_params.get('search','').strip()[:180]
        if query:
            try:document=normalize_document(query)
            except ModelValidationError:document=query
            search=Q(name__icontains=query)|Q(trade_name__icontains=query)|Q(contact_name__icontains=query)|Q(phone__icontains=query)|Q(email__icontains=query)
            if document:search |= Q(document__icontains=document)
            qs=qs.filter(search)
        pagination=SalesPagination();page=pagination.paginate_queryset(qs,request,view=self)
        response=pagination.get_paginated_response([output(s) for s in page])
        response.data['can_create']=request.user.has_perm('organizations.add_supplier')
        response.data['can_edit']=request.user.has_perm('organizations.change_supplier')
        response['Cache-Control']='no-store, private';return response

    def post(self,request,supplier_id=None):
        store=self.check_access();serializer=SupplierInput(data=request.data);serializer.is_valid(raise_exception=True)
        values=serializer.validated_data
        digest=hashlib.sha256(json.dumps({'supplier_id':supplier_id,'values':values},sort_keys=True,default=str).encode()).hexdigest()
        try:
            with model_errors():supplier=operate_supplier(user=request.user,store=store,supplier_id=supplier_id,values=values,digest=digest)
        except IntegrityError as exc:
            raise ValidationError('O documento ou envio conflitou com outro cadastro. Atualize a lista e confira também os inativos.') from exc
        return Response(output(supplier,True),headers={'Cache-Control':'no-store, private'})


class SupplierDetailView(SuppliersView):
    def get(self,request,supplier_id):
        supplier=get_object_or_404(Supplier,store=self.check_access(),pk=supplier_id)
        return Response(output(supplier,True),headers={'Cache-Control':'no-store, private'})
