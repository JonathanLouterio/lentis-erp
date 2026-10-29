"""Regras monetárias de entrada e acréscimo, sem gravação no banco."""
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from django.core.exceptions import ValidationError

FINANCED_KINDS = {'boleto', 'store_credit'}
IMMEDIATE_KINDS = {'cash', 'pix', 'transfer'}
CENT = Decimal('0.01')
ZERO = Decimal('0.00')


def financing_fees(rate, rows):
    """Rows: (kind, principal). Arredondamento comercial por forma de pagamento."""
    if not isinstance(rate, Decimal) or not rate.is_finite() or not ZERO <= rate <= 100 or rate != rate.quantize(CENT):
        raise ValidationError({'financing_rate': 'Informe um percentual de 0 a 100, com até duas casas decimais.'})
    if rate and not any(kind in FINANCED_KINDS and amount > 0 for kind, amount in rows):
        raise ValidationError({'financing_rate': 'O acréscimo exige saldo em boleto ou crediário.'})
    return [(amount * rate / 100).quantize(CENT, rounding=ROUND_HALF_UP) if kind in FINANCED_KINDS else ZERO for kind, amount in rows]


def validate_down_payment(base_total, rows):
    """Rows: (kind, principal, installment_count, confirmed).

    Uma única cobrança integral não é parcelamento. Entrada + saldo ou
    múltiplas linhas/parcelas são, independentemente de como foram divididas.
    """
    required = any(kind in FINANCED_KINDS for kind, _, _, _ in rows) and sum(count for _, _, count, _ in rows) > 1
    minimum = (base_total * Decimal('0.40')).quantize(CENT, rounding=ROUND_CEILING) if required else ZERO
    received = sum((amount for kind, amount, _, confirmed in rows if confirmed and kind in IMMEDIATE_KINDS), ZERO)
    if received < minimum:
        value = f'{minimum:.2f}'.replace('.', ',')
        raise ValidationError({'payments': f'Boleto ou crediário parcelado exige entrada recebida de pelo menos 40% (R$ {value}) do valor dos produtos após descontos. Confirme a entrada em dinheiro, Pix ou transferência, ou salve como rascunho.'})
    return minimum
