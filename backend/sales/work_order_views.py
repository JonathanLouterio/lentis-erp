import hashlib
import json
from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from .views import SalesBaseView, SalesPagination, model_errors
from .work_order_models import ServiceOrder
from .work_order_permissions import OrderActionPermission, order_capabilities, available_order_actions
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from .work_order_services import operate_order, NEXT
from .prescription_services import can_view_prescriptions, prescription_output


class OrderWriteSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    action = serializers.ChoiceField(choices=['create','update','advance','rework','cancel'])
    sale_id = serializers.IntegerField(min_value=1, required=False)
    expected_version = serializers.IntegerField(min_value=1, required=False)
    promised_on = serializers.DateField(required=False)
    laboratory = serializers.CharField(max_length=180,allow_blank=True,required=False)
    frame_description = serializers.CharField(max_length=255,allow_blank=True,required=False)
    lens_description = serializers.CharField(max_length=500,allow_blank=True,required=False)
    notes = serializers.CharField(max_length=4000,allow_blank=True,required=False)
    reason = serializers.CharField(max_length=1000,allow_blank=True,required=False)
    confirmed = serializers.BooleanField(required=False)
    target_status = serializers.ChoiceField(choices=['laboratory','mounting'],required=False)

    def validate(self, data):
        if data['action']=='create' and ('sale_id' not in data or 'promised_on' not in data):
            raise serializers.ValidationError('Informe a venda e a previsão de entrega.')
        if data['action']!='create' and 'expected_version' not in data:
            raise serializers.ValidationError('Informe a versão da OS.')
        return data


def output(order, user, detail=False):
    data = {'id':order.pk,'sale_id':order.sale_id,'sale_status':order.sale.status,'customer_name':order.snapshot.get('customer_name',''),
        'status':order.status,'status_label':order.get_status_display(),'version':order.version,
        'promised_on':order.promised_on,'laboratory':order.laboratory,'frame_description':order.frame_description,
        'lens_description':order.lens_description,'notes':order.notes,'created_at':order.created_at,'updated_at':order.updated_at,
        'overdue':order.status not in ('delivered','cancelled') and order.promised_on < timezone.localdate(),
        'has_prescription':bool(order.prescription_record_id),'next_status':NEXT.get(order.status),
        'actions':available_order_actions(order,user),
        'can_change':available_order_actions(order,user)['update']}
    if detail:
        data['items']=order.snapshot.get('items',[])
        data['prescription']=prescription_output(order.prescription_record) if can_view_prescriptions(user) else None
        data['can_view_prescription']=can_view_prescriptions(user)
        data['events']=[{'version':e.version,'action':e.action,'from_status':e.from_status,'to_status':e.to_status,'reason':e.reason,'snapshot':e.snapshot,'creator_username':e.created_by.username,'created_at':e.created_at} for e in order.events.select_related('created_by')]
    return data


@method_decorator(never_cache, name='dispatch')
class OrdersView(SalesBaseView):
    permission_classes = [OrderActionPermission]
    def check_access(self):
        store=self._selected_store()
        if not self.request.user.has_perm('sales.view_serviceorder'):
            raise PermissionDenied('Você não tem permissão de visualizar ordens de serviço.')
        return store

    def queryset(self,store):
        return ServiceOrder.objects.filter(sale__store=store).select_related('sale','prescription_record__created_by')

    def get(self,request):
        store=self.check_access(); qs=self.queryset(store)
        state=request.query_params.get('status','all')
        if state not in ['all','active',*ServiceOrder.Status.values]:
            raise ValidationError('Situação de OS inválida.')
        if state=='active':qs=qs.exclude(status__in=['delivered','cancelled'])
        elif state!='all':qs=qs.filter(status=state)
        sale=request.query_params.get('sale_id')
        if sale:
            try: sale=int(sale)
            except (ValueError,TypeError):raise ValidationError('Venda inválida.')
            if sale<1:raise ValidationError('Venda inválida.')
            qs=qs.filter(sale_id=sale)
        if request.query_params.get('overdue')=='1':qs=qs.exclude(status__in=['delivered','cancelled']).filter(promised_on__lt=timezone.localdate())
        pagination=SalesPagination(); page=pagination.paginate_queryset(qs,request,view=self)
        response=pagination.get_paginated_response([output(o,request.user) for o in page])
        response.data['can_create']=request.user.has_perm('sales.add_serviceorder')
        response['Cache-Control']='no-store, private'
        return response

    def post(self,request,order_id=None):
        store=self.check_access()
        s=OrderWriteSerializer(data=request.data);s.is_valid(raise_exception=True);values=s.validated_data
        if order_id:
            sale_id=get_object_or_404(self.queryset(store),pk=order_id).sale_id
        else:sale_id=values.get('sale_id')
        digest=hashlib.sha256(json.dumps({'order_id':order_id,'sale_id':sale_id,'values':values},sort_keys=True,default=str).encode()).hexdigest()
        try:
            with model_errors():
                order=operate_order(user=request.user,store=store,sale_id=sale_id,order_id=order_id,values=values,digest=digest)
        except IntegrityError as exc:
            raise ValidationError('O envio conflitou com outra operação. Reabra a OS para conferir o resultado.') from exc
        return Response(output(self.queryset(store).get(pk=order.pk),request.user,True),headers={'Cache-Control':'no-store, private'})


class OrderDetailView(OrdersView):
    def get(self,request,order_id):
        order=get_object_or_404(self.queryset(self.check_access()),pk=order_id)
        return Response(output(order,request.user,True),headers={'Cache-Control':'no-store, private'})


class OrderAccessView(OrdersView):
    def get(self,request):
        store=self.check_access()
        return Response({'store_id':store.pk,'actions':order_capabilities(request.user)})

class OrderSalesView(OrdersView):
    creation_options=True
    def get(self,request):
        from .models import Sale
        store=self.check_access()
        sales=Sale.objects.filter(store=store,status='completed',customer__isnull=False,service_order__isnull=True).select_related('customer').order_by('-pk')
        pagination=SalesPagination()
        page=pagination.paginate_queryset(sales,request,view=self)
        return pagination.get_paginated_response([{'id':s.pk,'customer_name':s.customer.name} for s in page])
