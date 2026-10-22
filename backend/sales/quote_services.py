from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from accounts.selectors import get_accessible_stores
from .quote_permissions import require_quote_action
from .models import Quote, QuoteItem, QuoteEvent, QuoteOperation, Sale, SaleItem


def operate_quote(*, user, store, quote_id, action, request_id, digest, validated_values):
    if not getattr(user,'is_authenticated',False):
        raise PermissionDenied('Entre com uma conta ativa.')
    with transaction.atomic():
        actor = get_user_model().objects.select_for_update(no_key=True).get(pk=user.pk)
        require_quote_action(actor,action,quote_id)
        user=actor
        if not user.is_active or not get_accessible_stores(user).filter(pk=store.pk).exists():
            raise PermissionDenied('O acesso à unidade não está mais disponível.')
        previous = QuoteOperation.objects.select_related('quote').filter(request_id=request_id).first()
        if previous:
            if previous.created_by_id != user.pk or previous.quote.store_id != store.pk:
                raise PermissionDenied('Esta operação pertence a outra conta ou unidade.')
            if previous.digest != digest: raise ValidationError('O identificador já foi usado com outros dados.')
            return previous.quote
        quote = None
        if quote_id:
            quote = Quote.objects.select_for_update(of=('self',)).filter(pk=quote_id, store=store).first()
            if quote is None: raise PermissionDenied('Orçamento não encontrado nesta unidade.')
            if action == 'convert' and quote.status == 'converted': return quote
        values = dict(validated_values())
        version = values.pop('expected_version', None)
        if quote is not None and version != quote.version:
            raise ValidationError('Este orçamento foi atualizado por outra operação. Reabra-o antes de continuar.')
        if action == 'save':
            if quote and quote.status in ('converted', 'rejected'):
                raise ValidationError('Um orçamento convertido ou recusado não pode ser substituído.')
            items = values.pop('items'); customer = values.pop('customer_id', None); discount = values.pop('discount_amount')
            if quote:
                quote.status = 'draft'; quote.customer = customer; quote.discount_amount = 0
                quote.valid_until = values['valid_until']; quote.notes = values['notes']; quote.version += 1
                quote.save(_allow_transition=True)
                for item in quote.items.all(): item.delete()
            else:
                quote = Quote.objects.create(store=store, created_by=user, customer=customer, discount_amount=0, **values)
            for value in items:
                value = dict(value); product = value.pop('product_id'); value.setdefault('unit_price', product.sale_price)
                QuoteItem.objects.create(quote=quote, product=product, **value)
            quote.discount_amount = discount
            quote.save()
            event = 'updated' if quote_id else 'created'
            reason = 'Edição dos termos; a proposta deve ser confirmada novamente.' if quote_id else ''
        else:
            if quote is None: raise ValidationError('Salve o orçamento antes de mudar sua situação.')
            reason = values.get('reason', '').strip()
            if action == 'reject':
                if quote.status not in ('draft','sent','accepted'): raise ValidationError('Esta proposta não pode ser recusada nesta situação.')
                if not reason: raise ValidationError({'reason': 'Informe o motivo da recusa.'})
                quote.status = 'rejected'
            elif action in ('send','accept','convert'):
                if quote.is_expired: raise ValidationError('O orçamento venceu. Edite a validade e confirme a proposta novamente.')
                if not quote.items.exists(): raise ValidationError('Adicione pelo menos um produto à proposta.')
                required = {'send': 'draft', 'accept': 'sent', 'convert': 'accepted'}[action]
                if quote.status != required: raise ValidationError('A situação atual não permite esta operação.')
                if action == 'send': quote.status = 'sent'
                elif action == 'accept': quote.status = 'accepted'
                else:
                    if quote.customer_id and not quote.customer.is_active: raise ValidationError('O cliente foi desativado. Edite a proposta antes da conversão.')
                    items = list(quote.items.select_related('product').order_by('product_id'))
                    if any(not item.product.is_active or item.product.store_id != store.pk for item in items):
                        raise ValidationError('Há produto inativo ou de outra unidade. Revise a proposta.')
                    sale = Sale.objects.create(store=store, customer=quote.customer, created_by=user, notes=quote.notes)
                    for item in items:
                        SaleItem.objects.create(sale=sale, product=item.product, quantity=item.quantity, unit_price=item.unit_price, discount_amount=item.discount_amount)
                    sale.discount_amount = quote.discount_amount; sale.save()
                    quote.sale = sale; quote.status = 'converted'
            else: raise ValidationError('Operação de orçamento inválida.')
            quote.version += 1; quote.save(_allow_transition=True); event = action
        QuoteEvent.objects.create(quote=quote, action=event, created_by=user, reason=reason, version=quote.version)
        QuoteOperation.objects.create(request_id=request_id, quote=quote, created_by=user, digest=digest)
        return quote
