from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from accounts.selectors import get_accessible_stores
from organizations.models import Product, Supplier
from organizations.stock_services import register_stock_movement
from .models import Purchase, PurchaseItem, PurchaseEvent, PurchaseStockMovement, PurchaseOperation


def operate_purchase(*,user,store,purchase_id,values,digest):
    with transaction.atomic():
        user=get_user_model().objects.select_for_update(no_key=True).get(pk=user.pk)
        if not get_accessible_stores(user).filter(pk=store.pk).exists():raise PermissionDenied('O acesso à unidade não está disponível.')
        permission='add' if purchase_id is None else 'change'
        if not user.has_perm('purchases.view_purchase') or not user.has_perm(f'purchases.{permission}_purchase'):raise PermissionDenied('Você não tem permissão para esta operação de compra.')
        action=values['action']
        if action=='receive' and not user.has_perm('purchases.receive_purchase'):raise PermissionDenied('Seu usuário não tem permissão de confirmar entrada de compra.')
        previous=PurchaseOperation.objects.select_related('purchase').filter(request_id=values['request_id']).first()
        if previous:
            if previous.created_by_id!=user.pk or previous.purchase.store_id!=store.pk:raise PermissionDenied('Este envio pertence a outra conta ou unidade.')
            if previous.digest!=digest:raise ValidationError('O identificador já foi utilizado com outros dados.')
            return previous.purchase
        if purchase_id is None:
            if action!='create':raise ValidationError('Crie um rascunho antes de confirmar a entrada.')
            purchase=Purchase(store=store,created_by=user,updated_by=user)
        else:
            purchase=get_object_or_404(Purchase.objects.select_for_update(),pk=purchase_id,store=store)
            if values.get('expected_version')!=purchase.version:raise ValidationError('A compra foi alterada. Reabra o rascunho antes de continuar.')
            if purchase.status!='draft':raise ValidationError('Compras confirmadas ou canceladas são somente leitura. Devoluções de compras serão tratadas em etapa própria.')
            if action=='create':raise ValidationError('Use a operação de edição para este rascunho.')
            purchase.version+=1;purchase.updated_by=user
        if action in ('create','update'):
            supplier=get_object_or_404(Supplier.objects.select_for_update(),pk=values['supplier_id'],store=store,is_active=True)
            purchase.supplier=supplier;purchase.reference=values.get('reference','').strip().upper()
            purchase.document_date=values.get('document_date');purchase.notes=values.get('notes','')
            duplicate=Purchase.objects.filter(store=store,supplier=supplier,reference=purchase.reference,status__in=['draft','received']).exclude(pk=purchase.pk)
            if purchase.reference and duplicate.exists():raise ValidationError({'reference':'Já existe uma compra com esta referência para o fornecedor na unidade.'})
            purchase.save(_service=True)
            if purchase.items.exists():purchase.items.all().delete()
            lines=values['items'];ids=[i['product_id'] for i in lines]
            if len(ids)!=len(set(ids)):raise ValidationError('Cada produto deve aparecer uma única vez na compra.')
            products={p.pk:p for p in Product.objects.filter(pk__in=ids,store=store,is_active=True)}
            if len(products)!=len(ids):raise ValidationError('Selecione produtos ativos da unidade da compra.')
            for line in lines:
                product=products[line['product_id']]
                PurchaseItem(purchase=purchase,product=product,product_code=product.internal_code,product_name=product.name,quantity=line['quantity'],unit_cost=line['unit_cost']).save(_service=True)
        elif action=='receive':
            if values.get('confirmed') is not True:raise ValidationError('Confirme a conferência das quantidades e custos antes de registrar a entrada.')
            supplier=get_object_or_404(Supplier.objects.select_for_update(),pk=purchase.supplier_id,store=store,is_active=True)
            lines=list(purchase.items.order_by('product_id'))
            if not lines:raise ValidationError('Adicione itens antes de confirmar a entrada.')
            ids=[line.product_id for line in lines]
            # Ordem de locks igual à utilizada nas vendas; evita inversão entre produtos.
            products={p.pk:p for p in Product.objects.select_for_update(of=('self',)).filter(pk__in=ids,store=store).order_by('pk')}
            for line in lines:
                product=products.get(line.product_id)
                if product is None or not product.is_active:raise ValidationError('Todos os produtos devem estar ativos e pertencer à unidade da compra.')
            for line in lines:
                movement=register_stock_movement(user=user,store_id=store.pk,product_id=line.product_id,movement_type='entry',quantity=line.quantity,reason=f'Entrada da compra #{purchase.pk}')
                PurchaseStockMovement(item=line,movement=movement).save(_service=True)
                if values.get('update_cost',False):Product.objects.filter(pk=line.product_id).update(cost_price=line.unit_cost,updated_at=timezone.now())
            purchase.supplier_snapshot={key:getattr(supplier,key) for key in ('name','trade_name','document','state_registration','phone','email','street','address_number','city','state')}
            purchase.updates_cost=values.get('update_cost',False)
            purchase.status='received';purchase.received_by=user;purchase.received_at=timezone.now()
            purchase.save(_service=True)
        elif action=='cancel':
            if not values.get('reason','').strip():raise ValidationError('Informe o motivo do cancelamento do rascunho.')
            purchase.status='cancelled';purchase.save(_service=True)
        else:raise ValidationError('Operação de compra inválida.')
        PurchaseEvent(purchase=purchase,version=purchase.version,action=action,reason=values.get('reason','').strip(),created_by=user).save(_service=True)
        PurchaseOperation(request_id=values['request_id'],purchase=purchase,created_by=user,digest=digest).save(_service=True)
        return purchase
