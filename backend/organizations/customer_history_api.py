from decimal import Decimal
from django.db.models import DecimalField, F, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from sales.models import Sale, Quote, Receivable, FinancialEntry, ServiceOrder
from sales.views import SalesBaseView, SalesPagination
from .models import Customer, Prescription
from .serializers import CustomerSerializer
from .prescription_api import snapshot as prescription_snapshot

ZERO = Decimal('0.00')


def receivables(customer):
    amount = DecimalField(max_digits=28, decimal_places=2)
    received = FinancialEntry.objects.filter(receivable_id=OuterRef('pk')).order_by().values('receivable_id').annotate(total=Sum('amount')).values('total')
    return Receivable.objects.filter(payment__sale__store_id=customer.store_id,payment__sale__customer_id=customer.pk).select_related('payment__sale','payment__method').annotate(
        received_total=Coalesce(Subquery(received,output_field=amount),Value(ZERO),output_field=amount),
    ).annotate(open_amount=F('amount')-F('received_total'))


def money(value):
    return f'{value:.2f}'


def item_rows(items):
    return [{'name':i.product_name,'code':i.product_code,'quantity':str(i.quantity),'unit_price':money(i.unit_price),'total':money(i.total)} for i in items]


def row(record, section, detail=False):
    result={'id':record.pk,'kind':section,'fields':[],'items':[],'clinical':None}
    if section=='sales':
        result.update(date=record.created_at,title=f'Venda #{record.pk}',status=record.status,status_label=record.get_status_display(),amount=money(record.total),sale_id=record.pk)
        if detail:
            result['items']=item_rows(record.items.all())
            result['fields']=[{'label':'Observações','value':record.notes},{'label':'Cancelamento','value':record.cancellation_reason}]
            result['fields'] += [{'label':f'Pagamento · {p.method.name}','value':money(p.amount)} for p in record.payments.all()]
    elif section=='quotes':
        result.update(date=record.created_at,title=f'Orçamento #{record.pk}',status=record.status,status_label=record.get_status_display(),amount=money(record.total),sale_id=record.sale_id)
        if detail:
            result['items']=item_rows(record.items.all())
            result['fields']=[{'label':'Validade','value':str(record.valid_until)},{'label':'Observações','value':record.notes}]
    elif section=='prescriptions':
        result.update(date=record.created_at,title=f'Receita #{record.pk}',status='active' if record.is_active else 'archived',status_label='Ativa' if record.is_active else 'Arquivada',amount=None,sale_id=None)
        result['fields']=[{'label':'Data da receita','value':str(record.issued_on)},{'label':'Versão','value':str(record.version)}]
        if detail:
            result['clinical']=prescription_snapshot(record)
            result['fields'] += [{'label':'Prescritor','value':record.prescriber_name},{'label':'Registro','value':record.prescriber_registration},{'label':'Observações','value':record.notes}]
    elif section=='orders':
        result.update(date=record.created_at,title=f'OS #{record.pk}',status=record.status,status_label=record.get_status_display(),amount=None,sale_id=record.sale_id)
        result['fields']=[{'label':'Previsão de entrega','value':str(record.promised_on)},{'label':'Laboratório','value':record.laboratory}]
        if detail:
            result['fields'] += [{'label':'Armação','value':record.frame_description},{'label':'Lentes','value':record.lens_description},{'label':'Observações operacionais','value':record.notes}]
            result['items']=[{'name':i['name'],'code':i['code'],'quantity':i['quantity'],'unit_price':None,'total':None} for i in record.snapshot.get('items',[])]
    else:
        cancelled=record.payment.sale.status=='cancelled'
        remaining=ZERO if cancelled else record.open_amount
        state='cancelled' if cancelled else 'paid' if remaining==0 else 'partial' if record.received_total>0 else 'pending'
        result.update(date=record.created_at,title=f'Parcela {record.number} · venda #{record.payment.sale_id}',status=state,status_label={'cancelled':'Cancelada','paid':'Quitada','partial':'Parcial','pending':'Pendente'}[state],amount=money(record.amount),sale_id=record.payment.sale_id,
            remaining=money(remaining),due_date=record.due_date,debtor=record.debtor,overdue=not cancelled and remaining>0 and record.due_date<timezone.localdate())
        result['fields']=[{'label':'Responsável','value':record.get_debtor_display()},{'label':'Forma de pagamento','value':record.payment.method.name}]
        if detail:
            result['fields'] += [{'label':('Estorno' if e.amount<0 else 'Recebimento')+f' · {e.created_at:%d/%m/%Y} · {e.method.name}','value':money(e.amount)} for e in record.entries.select_related('method').order_by('created_at','pk')]
    return result


class CustomerHistoryView(SalesBaseView):
    def get(self,request,customer_id):
        store=self._selected_store()
        # Inativos também mantêm seu histórico; a identidade e a unidade são sempre obrigatórias.
        customer=get_object_or_404(Customer,pk=customer_id,store=store)
        section=request.query_params.get('section','summary')
        if section not in ('summary','sales','quotes','prescriptions','orders','installments'):
            raise ValidationError({'section':'Seção de histórico inválida.'})
        from organizations.access_permissions import fresh_actor
        actor=fresh_actor(request)
        can_quotes=bool(actor and actor.has_perm('sales.view_quote'))
        if section=='quotes' and not can_quotes:
            raise PermissionDenied('Você não tem permissão de consultar orçamentos.')
        can_rx=request.user.has_perm('organizations.view_prescription')
        can_orders=request.user.has_perm('sales.view_serviceorder')
        if section=='prescriptions' and not can_rx:
            raise PermissionDenied('Você não tem permissão de consultar receitas.')
        if section=='orders' and not can_orders:
            raise PermissionDenied('Você não tem permissão de consultar ordens de serviço.')
        sales=Sale.objects.filter(store=store,customer=customer)
        quotes=Quote.objects.filter(store=store,customer=customer)
        orders=ServiceOrder.objects.filter(sale__store=store,sale__customer=customer)
        prescriptions=Prescription.objects.filter(store=store,customer=customer)
        installments=receivables(customer)
        headers={'Cache-Control':'no-store, private'}
        if section=='summary':
            pending=installments.filter(payment__sale__status='completed',open_amount__gt=0)
            totals={}
            for debtor in ('customer','operator'):
                qs=pending.filter(debtor=debtor)
                totals[debtor]=money(qs.aggregate(total=Sum('open_amount'))['total'] or ZERO)
            overdue=pending.filter(debtor='customer',due_date__lt=timezone.localdate())
            return Response({'customer':CustomerSerializer(customer).data,'generated_at':timezone.now(),
                'permissions':{'quotes':can_quotes,'prescriptions':can_rx,'orders':can_orders},
                'summary':{'completed_sales':sales.filter(status='completed').count(),'draft_sales':sales.filter(status='draft').count(),'quotes':quotes.count() if can_quotes else None,
                    'orders':orders.count() if can_orders else None,'prescriptions':prescriptions.count() if can_rx else None,
                    'customer_pending':totals['customer'],'operator_pending':totals['operator'],
                    'customer_overdue':money(overdue.aggregate(total=Sum('open_amount'))['total'] or ZERO)}},headers=headers)
        qs={'sales':sales.select_related('created_by').prefetch_related('items','payments__method'),
            'quotes':quotes.prefetch_related('items'), 'orders':orders,
            'prescriptions':prescriptions,'installments':installments}[section].order_by('-created_at','-pk')
        record_id=request.query_params.get('record_id')
        if record_id is not None:
            try:record_id=int(record_id)
            except (ValueError,TypeError):raise ValidationError('Registro inválido.')
            if record_id<1:raise ValidationError('Registro inválido.')
            return Response(row(get_object_or_404(qs,pk=record_id),section,True),headers=headers)
        pagination=SalesPagination();page=pagination.paginate_queryset(qs,request,view=self)
        response=pagination.get_paginated_response([row(r,section) for r in page]);response['Cache-Control']=headers['Cache-Control']
        return response
