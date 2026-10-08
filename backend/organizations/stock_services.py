from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from accounts.selectors import get_accessible_stores

from .models import Product, StockMovement


def register_stock_movement(*, user, store_id, product_id, movement_type, quantity, reason):
    """Registra o histórico e atualiza o saldo em uma única transação.

    Entrada/saída: quantity é a quantidade movimentada, sempre positiva.
    Ajuste: quantity é o saldo contado, incluindo zero.
    """
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        raise PermissionDenied("Entre com uma conta ativa para movimentar estoque.")
    if not get_accessible_stores(user).filter(pk=store_id).exists():
        raise PermissionDenied("Você não possui acesso a esta unidade.")

    if movement_type not in StockMovement.MovementType.values:
        raise ValidationError({"movement_type": "Informe um tipo de movimentação válido."})

    try:
        amount = Decimal(str(quantity))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({"quantity": "Informe uma quantidade válida."}) from exc
    if not amount.is_finite():
        raise ValidationError({"quantity": "Informe uma quantidade finita."})
    if amount < 0 or (movement_type != StockMovement.MovementType.ADJUSTMENT and amount == 0):
        raise ValidationError({"quantity": "Entrada e saída devem ser positivas; ajuste aceita zero."})
    if amount > Decimal("999999999.999"):
        raise ValidationError({"quantity": "A quantidade excede o limite permitido."})
    if amount != amount.quantize(Decimal("0.001")):
        raise ValidationError({"quantity": "Use no máximo três casas decimais."})
    amount = amount.quantize(Decimal("0.001"))
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError({"reason": "Informe o motivo da movimentação."})

    with transaction.atomic():
        # Serializa operações simultâneas no mesmo produto no PostgreSQL.
        product = Product.objects.select_for_update().filter(
            pk=product_id, store_id=store_id, is_active=True,
        ).first()
        if product is None:
            raise ValidationError({"product": "Produto ativo não encontrado nesta unidade."})

        before = product.stock_quantity
        if movement_type == StockMovement.MovementType.ENTRY:
            after = before + amount
        elif movement_type == StockMovement.MovementType.EXIT:
            after = before - amount
        else:
            after = amount
        if after < 0:
            raise ValidationError({"quantity": "Estoque insuficiente para esta saída."})
        if after > Decimal("999999999.999"):
            raise ValidationError({"quantity": "O saldo resultante excede o limite permitido."})

        movement = StockMovement(
            store_id=product.store_id, product=product,
            movement_type=movement_type, quantity=amount,
            balance_before=before, balance_after=after,
            reason=reason.strip(), created_by=user,
        )
        movement.full_clean()
        movement.save()
        product.stock_quantity = after
        product.save(update_fields=["stock_quantity", "updated_at"])
        return movement
