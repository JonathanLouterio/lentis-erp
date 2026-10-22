import hashlib
import json
from decimal import Decimal
from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from sales.views import SalesBaseView, SalesPagination, model_errors
from .models import Purchase
from .access_permissions import PurchaseActionPermission, purchase_capabilities, payable_capabilities, available_purchase_actions
from .services import operate_purchase


class ItemInput(serializers.Serializer):
    product_id=serializers.IntegerField(min_value=1,max_value=9223372036854775807)
    quantity=serializers.DecimalField(max_digits=12,decimal_places=3,min_value=Decimal('0.001'))
    unit_cost=serializers.DecimalField(max_digits=12,decimal_places=2,min_value=Decimal('0'))


class PurchaseInput(serializers.Serializer):
    request_id=serializers.UUIDField()
    expected_version=serializers.IntegerField(min_value=1,required=False)
    action=serializers.ChoiceField(choices=['create','update','receive','cancel'])
    supplier_id=serializers.IntegerField(min_value=1,max_value=9223372036854775807,required=False)
    reference=serializers.CharField(max_length=60,allow_blank=True,required=False)
    document_date=serializers.DateField(allow_null=True,required=False)
    notes=serializers.CharField(max_length=4000,allow_blank=True,required=False)
    reason=serializers.CharField(max_length=255,allow_blank=True,required=False)
    confirmed=serializers.BooleanField(required=False)
    update_cost=serializers.BooleanField(required=False)
    items=ItemInput(many=True,allow_empty=False,max_length=100,required=False)

    def validate(self,values):
        if values['action'] in ('create','update') and ('supplier_id' not in values or 'items' not in values):raise serializers.ValidationError('Informe o fornecedor e ao menos um item.')
        if values['action']!='create' and 'expected_version' not in values:raise serializers.ValidationError('Informe a versão da compra.')
        return values


def output(purchase,user,detail=False):
    result={'id':purchase.pk,'store':purchase.store_id,'supplier_id':purchase.supplier_id,'supplier_name':purchase.supplier_snapshot.get('name',purchase.supplier.name),
        'status':purchase.status,'status_label':purchase.get_status_display(),'version':purchase.version,'reference':purchase.reference,'document_date':purchase.document_date,'notes':purchase.notes,
        'total':f'{purchase.total:.2f}','updates_cost':purchase.updates_cost,'created_at':purchase.created_at,'received_at':purchase.received_at,
        'actions':available_purchase_actions(purchase,user),
        'can_edit':available_purchase_actions(purchase,user)['update'],'can_receive':available_purchase_actions(purchase,user)['receive']}
    if detail:
        result['supplier_snapshot']=purchase.supplier_snapshot
        result['items']=[{'id':i.pk,'product_id':i.product_id,'product_code':i.product_code,'product_name':i.product_name,'quantity':str(i.quantity),'unit_cost':str(i.unit_cost),'total':f'{i.total:.2f}','movement_id':getattr(getattr(i,'stock_link',None),'movement_id',None)} for i in purchase.items.all()]
        result['events']=[{'action':e.action,'action_label':e.get_action_display(),'reason':e.reason,'version':e.version,'creator_username':e.created_by.username,'created_at':e.created_at} for e in purchase.events.select_related('created_by')]
    return result


class PurchasesView(SalesBaseView):
    permission_classes=[PurchaseActionPermission]
    def finalize_response(self,request,response,*args,**kwargs):
        response=super().finalize_response(request,response,*args,**kwargs)
        response['Cache-Control']='no-store, private'
        return response
    def check_access(self):
        store=self._selected_store()
        if not self.request.user.has_perm('purchases.view_purchase'):raise PermissionDenied('Seu usuário precisa da permissão de visualizar compras.')
        return store

    def queryset(self,store):
        return Purchase.objects.filter(store=store).select_related('supplier').prefetch_related('items__stock_link')

    def get(self,request):
        qs=self.queryset(self.check_access());state=request.query_params.get('status','all')
        if state not in ('all',*Purchase.Status.values):raise ValidationError('Situação de compra inválida.')
        if state!='all':qs=qs.filter(status=state)
        pagination=SalesPagination();page=pagination.paginate_queryset(qs,request,view=self)
        response=pagination.get_paginated_response([output(p,request.user) for p in page])
        response.data['can_create']=request.user.has_perm('purchases.add_purchase')
        response.data['can_receive']=purchase_capabilities(request.user)['receive']
        response['Cache-Control']='no-store, private';return response

    def post(self,request,purchase_id=None):
        store=self.check_access();serializer=PurchaseInput(data=request.data);serializer.is_valid(raise_exception=True);values=serializer.validated_data
        digest=hashlib.sha256(json.dumps({'purchase_id':purchase_id,'values':values},sort_keys=True,default=str).encode()).hexdigest()
        try:
            with model_errors():purchase=operate_purchase(user=request.user,store=store,purchase_id=purchase_id,values=values,digest=digest)
        except IntegrityError as exc:raise ValidationError('O envio ou a referência conflitou com outra compra. Atualize a lista antes de continuar.') from exc
        return Response(output(self.queryset(store).get(pk=purchase.pk),request.user,True),headers={'Cache-Control':'no-store, private'})


class PurchaseDetailView(PurchasesView):
    def get(self,request,purchase_id):
        return Response(output(get_object_or_404(self.queryset(self.check_access()),pk=purchase_id),request.user,True),headers={'Cache-Control':'no-store, private'})


class PurchaseAccessView(PurchasesView):
    access_only=True
    http_method_names=['get','head','options']
    def get(self,request):
        store=self._selected_store()
        return Response({'store_id':store.pk,'purchases':purchase_capabilities(request.user),'payables':payable_capabilities(request.user)})

class PurchaseOptionsView(PurchasesView):
    catalog_options=True
    http_method_names=['get','head','options']
    def get(self,request):
        from organizations.models import Supplier, Product
        store=self.check_access()
        pagination=SalesPagination()
        suppliers=pagination.paginate_queryset(Supplier.objects.filter(store=store,is_active=True).order_by('name','pk'),request,view=self)
        response=pagination.get_paginated_response([{'id':s.pk,'name':s.name,'document':s.document} for s in suppliers])
        response.data['products']=[{'id':p.pk,'internal_code':p.internal_code,'name':p.name,'cost_price':str(p.cost_price)} for p in Product.objects.filter(store=store,is_active=True).order_by('internal_code','pk')]
        return response
