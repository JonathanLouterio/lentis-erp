from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from accounts.selectors import get_accessible_stores
from .work_order_permissions import require_order_action
from .models import Sale
from .work_order_models import ServiceOrder, ServiceOrderEvent, ServiceOrderOperation

FIELDS = ('promised_on','laboratory','frame_description','lens_description','notes')
NEXT = {'open':'laboratory','laboratory':'mounting','mounting':'checking','checking':'ready','ready':'delivered'}


def order_fields(order):
    return {key: str(getattr(order,key)) for key in FIELDS}


def operate_order(*, user, store, sale_id, order_id, values, digest):
    if not user or not user.is_authenticated:
        raise PermissionDenied('A autenticação é obrigatória.')
    with transaction.atomic():
        user = get_user_model().objects.select_for_update(no_key=True).get(pk=user.pk)
        if not user.is_active or not get_accessible_stores(user).filter(pk=store.pk).exists():
            raise PermissionDenied('O acesso à unidade não está disponível.')
        require_order_action(user, values.get('action'))
        previous = ServiceOrderOperation.objects.select_related('order__sale').filter(request_id=values['request_id']).first()
        if previous:
            if previous.created_by_id != user.pk or previous.order.sale.store_id != store.pk:
                raise PermissionDenied('Este envio pertence a outra conta ou unidade.')
            if previous.digest != digest:
                raise ValidationError('Este identificador já foi usado com outros dados.')
            return previous.order
        # A venda é travada antes da OS; o cancelamento da venda usa o mesmo lock.
        sale = Sale.objects.select_for_update(of=('self',)).filter(pk=sale_id, store=store).first()
        if sale is None:
            raise PermissionDenied('Venda não encontrada nesta unidade.')
        order = ServiceOrder.objects.select_for_update().filter(sale=sale).first()
        action = values['action']
        reason = values.get('reason','').strip()
        old_status = order.status if order else ''
        if order_id is None:
            if order:
                raise ValidationError(f'Esta venda já possui a OS #{order.pk}. Abra a ordem existente.')
            if action != 'create' or sale.status != 'completed' or not sale.customer_id:
                raise ValidationError('Crie a OS a partir de uma venda finalizada com cliente identificado.')
            if not sale.items.exists():
                raise ValidationError('A venda deve possuir itens.')
            order = ServiceOrder(sale=sale, prescription_record_id=sale.prescription_record_id, created_by=user,
                snapshot={'customer_id':sale.customer_id,'customer_name':sale.customer.name,
                    'items':[{'product_id':i.product_id,'code':i.product_code,'name':i.product_name,'quantity':str(i.quantity)} for i in sale.items.all()]})
            for key in FIELDS:
                setattr(order,key,values.get(key,''))
        else:
            if order is None or order.pk != order_id:
                raise PermissionDenied('Ordem não encontrada nesta unidade.')
            if values.get('expected_version') != order.version:
                raise ValidationError('Esta OS foi atualizada. Reabra a ordem antes de continuar.')
            if order.status in ('delivered','cancelled'):
                raise ValidationError('Uma OS entregue ou cancelada não pode ser alterada.')
            if sale.status != 'completed' and action != 'cancel':
                raise ValidationError('A venda foi cancelada. Cancele a OS e confira a operação.')
            if action == 'update':
                if not reason:
                    raise ValidationError('Informe o motivo da alteração.')
                for key in FIELDS:
                    if key in values:
                        setattr(order,key,values[key])
            elif action == 'advance':
                if order.status == 'checking' and values.get('confirmed') is not True:
                    raise ValidationError('Confirme a conferência antes de liberar para entrega.')
                if order.status == 'ready' and (values.get('confirmed') is not True or not reason):
                    raise ValidationError('Confirme a entrega e informe quem recebeu.')
                order.status = NEXT[order.status]
            elif action == 'rework':
                if order.status not in ('checking','ready') or values.get('target_status') not in ('laboratory','mounting') or not reason:
                    raise ValidationError('O retrabalho deve partir da conferência ou da entrega, com destino e motivo.')
                order.status = values['target_status']
            elif action == 'cancel':
                if not reason:
                    raise ValidationError('Informe o motivo do cancelamento da OS.')
                order.status = 'cancelled'
            else:
                raise ValidationError('Operação inválida para esta OS.')
            order.version += 1
        order.save(_service=True)
        ServiceOrderEvent.objects.create(order=order,version=order.version,action=action,from_status=old_status,to_status=order.status,reason=reason,snapshot=order_fields(order),created_by=user)
        ServiceOrderOperation.objects.create(request_id=values['request_id'],order=order,created_by=user,digest=digest)
        return order
