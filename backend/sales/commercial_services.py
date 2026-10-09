import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from accounts.models import StoreMembership
from accounts.selectors import get_accessible_stores
from .models import DiscountAuthorization, DiscountPolicy, Sale


ZERO = Decimal('0.00')


def current_policy(user, store):
    if not getattr(user,'is_authenticated',False) or not user.is_active or not get_accessible_stores(user).filter(pk=store.pk).exists():
        raise PermissionDenied('Você não possui acesso ativo a esta unidade.')
    if user.is_superuser:
        return 'superuser', Decimal('100.00'), False
    membership = StoreMembership.objects.filter(user=user, store=store, is_active=True).first()
    if membership is None:
        raise PermissionDenied('O vínculo com a unidade não está ativo.')
    policy = DiscountPolicy.objects.filter(store=store,role=membership.role).first()
    return membership.role, policy.limit_percentage if policy else Decimal('100.00'), policy is not None


def can_approve(user, store):
    return bool(user.is_authenticated and user.is_active and user.has_perm('sales.approve_discount')
        and get_accessible_stores(user).filter(pk=store.pk).exists())


def discount_snapshot(sale, user):
    role, limit, configured = current_policy(user, sale.store)
    items = sorted(sale.items.all(),key=lambda item:item.product_id)
    reference = sum(((item.quantity * max(item.reference_price if item.reference_price is not None else item.unit_price, item.unit_price)).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP) for item in items), ZERO)
    discount = reference - sale.total
    data = {'store':sale.store_id,'user':user.pk,'role':role,'limit':str(limit.quantize(Decimal('0.01'))),
        'customer':sale.customer_id,'discount':str(sale.discount_amount.quantize(Decimal('0.01'))),
        'items':[[item.product_id,str(item.quantity.quantize(Decimal('0.001'))),str(item.unit_price.quantize(Decimal('0.01'))),
            str(item.discount_amount.quantize(Decimal('0.01'))),str((item.reference_price if item.reference_price is not None else item.unit_price).quantize(Decimal('0.01')))] for item in items]}
    fingerprint = hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    percentage = (discount * 100 / reference).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP) if reference else ZERO
    return {'hash':fingerprint,'role':role,'limit':limit,'configured':configured,'reference':reference,'discount':discount,
        'percentage':percentage,'required':discount * 100 > reference * limit}


def current_request(sale,user,snapshot):
    return sale.discount_authorizations.filter(action='request',created_by=user,snapshot_hash=snapshot['hash']).order_by('-pk').first()


def decision_for(request):
    return DiscountAuthorization.objects.filter(request=request).select_related('created_by').first() if request else None


def validate_discount(sale, user):
    snapshot = discount_snapshot(sale,user)
    if not snapshot['required']:
        return
    request = current_request(sale,user,snapshot)
    decision = decision_for(request)
    if decision is None or decision.action != 'approve':
        raise ValidationError({'discount_amount':f'Desconto acima do limite de {snapshot["limit"]}%. Salve o rascunho e solicite autorização.'})


def reason_text(reason):
    if not isinstance(reason,str) or not reason.strip() or len(reason.strip()) > 255:
        raise ValidationError({'reason':'Informe um motivo com até 255 caracteres.'})
    return reason.strip()


def request_discount(*,user,sale_id,reason):
    from .services import _locked_sale
    reason = reason_text(reason)
    with transaction.atomic():
        sale = _locked_sale(user,sale_id)
        if sale.status != Sale.Status.DRAFT:
            raise ValidationError('Solicitações são permitidas somente em rascunhos.')
        snapshot = discount_snapshot(sale,user)
        if not snapshot['required']:
            raise ValidationError('O desconto está dentro do limite deste perfil.')
        existing = current_request(sale,user,snapshot)
        decision = decision_for(existing)
        if existing and (decision is None or decision.action == 'approve'):
            return sale
        DiscountAuthorization.objects.create(sale=sale,action='request',created_by=user,reason=reason,
            snapshot_hash=snapshot['hash'],role=snapshot['role'],limit_percentage=snapshot['limit'],
            reference_subtotal=snapshot['reference'],discount_amount=snapshot['discount'])
        return sale


def decide_discount(*,user,sale_id,request_id,action,reason):
    from .services import _locked_sale
    reason = reason_text(reason)
    if action not in ('approve','reject'):
        raise ValidationError({'action':'Escolha autorizar ou recusar.'})
    with transaction.atomic():
        sale = _locked_sale(user,sale_id)
        if not can_approve(user,sale.store):
            raise PermissionDenied('Sua conta não possui permissão para autorizar descontos.')
        if sale.status != Sale.Status.DRAFT:
            raise ValidationError('Somente solicitações de rascunhos podem ser decididas.')
        request = sale.discount_authorizations.select_related('created_by').filter(pk=request_id,action='request').first()
        if request is None:
            raise ValidationError('Solicitação não encontrada nesta venda.')
        if request.created_by_id == user.pk:
            raise PermissionDenied('A autorização deve ser feita por outra pessoa.')
        snapshot = discount_snapshot(sale,request.created_by)
        if snapshot['hash'] != request.snapshot_hash or not snapshot['required']:
            raise ValidationError('A venda, o perfil ou o limite mudou. Solicite uma nova autorização.')
        existing = decision_for(request)
        if existing:
            if existing.action != action:
                raise ValidationError('Esta solicitação já possui outra decisão registrada.')
            return sale
        DiscountAuthorization.objects.create(sale=sale,request=request,action=action,created_by=user,reason=reason,
            snapshot_hash=request.snapshot_hash,role=request.role,limit_percentage=request.limit_percentage,
            reference_subtotal=request.reference_subtotal,discount_amount=request.discount_amount)
        return sale


def discount_control(sale,user):
    if sale.status != Sale.Status.DRAFT:
        return None
    snapshot = discount_snapshot(sale,user)
    request = current_request(sale,user,snapshot)
    decision = decision_for(request)
    state = 'not_required' if not snapshot['required'] else 'required' if not request else 'pending' if not decision else 'approved' if decision.action == 'approve' else 'rejected'
    return {'required':snapshot['required'],'limit_percentage':str(snapshot['limit']),'discount_percentage':str(snapshot['percentage']),
        'reference_subtotal':str(snapshot['reference']),'discount_amount':str(snapshot['discount']),
        'state':state,'request_id':request.pk if request else None}


def authorization_history(sale,user):
    result = []
    for request in sale.discount_authorizations.filter(action='request').select_related('created_by'):
        decision = decision_for(request)
        try:
            current = sale.status == 'draft' and discount_snapshot(sale,request.created_by)['hash'] == request.snapshot_hash
        except PermissionDenied:
            current = False
        result.append({'id':request.pk,'requester':request.created_by.username,'reason':request.reason,'created_at':request.created_at,
            'limit_percentage':str(request.limit_percentage),'reference_subtotal':str(request.reference_subtotal),'discount_amount':str(request.discount_amount),
            'state':decision.action if decision else 'pending','current':current,
            'can_decide':current and decision is None and user.pk != request.created_by_id and can_approve(user,sale.store),
            'decided_by':decision.created_by.username if decision else None,'decision_reason':decision.reason if decision else None,'decided_at':decision.created_at if decision else None})
    return result
