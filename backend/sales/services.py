from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.selectors import get_accessible_stores
from organizations.models import Product, StockMovement
from organizations.stock_services import register_stock_movement

from .models import Sale, SaleEvent, SaleStockMovement


def _locked_sale(user, sale_id):
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        raise PermissionDenied("Entre com uma conta ativa para operar vendas.")
    try:
        sale_id = int(sale_id)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"sale": "Informe uma venda válida."}) from exc
    if not 0 < sale_id <= 9223372036854775807:
        raise ValidationError({"sale": "Informe uma venda válida."})
    # A unidade é verificada em cada pedido, inclusive nas repetições.
    sale = Sale.objects.select_for_update(of=("self",)).filter(
        pk=sale_id, store__in=get_accessible_stores(user),
    ).first()
    if sale is None:
        raise PermissionDenied("Venda não encontrada nas unidades autorizadas para sua conta.")
    return sale


def _lock_products(product_ids):
    # A mesma ordem em todas as vendas evita locks em ordem inversa.
    return {product.pk: product for product in Product.objects.select_for_update(of=("self",)).filter(
        pk__in=product_ids,
    ).order_by("pk")}


def finalize_sale(*, user, sale_id):
    with transaction.atomic():
        sale = _locked_sale(user, sale_id)
        if sale.status == Sale.Status.COMPLETED:
            if not sale.events.filter(event_type=SaleEvent.EventType.COMPLETED).exists():
                raise ValidationError("O histórico de finalização desta venda está incompleto.")
            return sale
        if sale.status != Sale.Status.DRAFT:
            raise ValidationError("Uma venda cancelada não pode ser finalizada.")
        if sale.events.exists():
            raise ValidationError("O histórico não corresponde a uma venda em rascunho.")
        sale.full_clean()
        if sale.payments.exists():
            from .payment_services import validate_payments
            validate_payments(sale)
        items = list(sale.items.select_for_update(of=("self",)).order_by("product_id"))
        if not items:
            raise ValidationError({"items": "Adicione pelo menos um produto à venda."})
        products = _lock_products(item.product_id for item in items)
        for item in items:
            product = products.get(item.product_id)
            if product is None or product.store_id != sale.store_id or not product.is_active:
                raise ValidationError({"items": "Todos os produtos devem estar ativos e pertencer à unidade da venda."})
            item.sale = sale
            item.product = product
            item.full_clean()
            if product.stock_quantity < item.quantity and not sale.store.allow_negative_stock:
                raise ValidationError({"items": f"Estoque insuficiente para {item.product_code} — {item.product_name}."})

        event = SaleEvent.objects.create(sale=sale, event_type=SaleEvent.EventType.COMPLETED, created_by=user)
        for item in items:
            movement = register_stock_movement(
                user=user, store_id=sale.store_id, product_id=item.product_id,
                movement_type=StockMovement.MovementType.EXIT, quantity=item.quantity,
                reason=f"Finalização da venda #{sale.pk}; item #{item.pk}.",
            )
            SaleStockMovement.objects.create(event=event, item=item, movement=movement)
        sale.status = Sale.Status.COMPLETED
        sale.completed_at = timezone.now()
        sale.save(_allow_status_change=True, update_fields=["status", "completed_at", "updated_at"])
        if sale.payments.exists():
            from .payment_services import book_sale_payments
            book_sale_payments(sale, user)
        return sale


def cancel_sale(*, user, sale_id, reason):
    if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 255:
        raise ValidationError({"reason": "Informe um motivo de cancelamento com até 255 caracteres."})
    reason = reason.strip()
    with transaction.atomic():
        sale = _locked_sale(user, sale_id)
        if sale.completed_at is not None and not (user.is_staff or user.is_superuser):
            raise PermissionDenied("Somente administradores podem cancelar uma venda finalizada.")
        if sale.status == Sale.Status.CANCELLED:
            if not sale.events.filter(event_type=SaleEvent.EventType.CANCELLED).exists():
                raise ValidationError("O histórico de cancelamento desta venda está incompleto.")
            return sale

        completed = sale.status == Sale.Status.COMPLETED
        links = []
        if completed:
            completed_event = sale.events.filter(event_type=SaleEvent.EventType.COMPLETED).first()
            if completed_event is None:
                raise ValidationError("O histórico de finalização desta venda está incompleto.")
            links = list(completed_event.stock_movements.select_related("item", "movement").order_by("item__product_id"))
            item_ids = set(sale.items.values_list("pk", flat=True))
            if not item_ids or {link.item_id for link in links} != item_ids:
                raise ValidationError("O histórico das baixas desta venda está incompleto.")
            _lock_products(link.movement.product_id for link in links)
        elif sale.status != Sale.Status.DRAFT or sale.events.exists():
            raise ValidationError("A situação e o histórico da venda são incompatíveis.")

        event = SaleEvent.objects.create(
            sale=sale, event_type=SaleEvent.EventType.CANCELLED, created_by=user, reason=reason,
        )
        for link in links:
            link.full_clean()
            movement = register_stock_movement(
                user=user, store_id=sale.store_id, product_id=link.movement.product_id,
                movement_type=StockMovement.MovementType.ENTRY, quantity=link.movement.quantity,
                reason=f"Cancelamento da venda #{sale.pk}; item #{link.item_id}. {reason}"[:255],
                _allow_inactive=True,
            )
            SaleStockMovement.objects.create(event=event, item=link.item, movement=movement)
        from .payment_services import reverse_sale_financials
        reverse_sale_financials(sale, user, reason)
        sale.status = Sale.Status.CANCELLED
        sale.cancelled_at = timezone.now()
        sale.cancellation_reason = reason
        sale.save(_allow_status_change=True, update_fields=["status", "cancelled_at", "cancellation_reason", "updated_at"])
        return sale
