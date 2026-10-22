"""O lock da conta serializa abertura, fechamento e lançamento no caixa físico."""
from decimal import Decimal
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from accounts.selectors import get_accessible_stores
from .finance_permissions import require_finance
from .models import CashPosting, CashSession, FinancialAccount


def authorized(user, store):
    if not getattr(user, 'is_authenticated', False) or not user.is_active or not get_accessible_stores(user).filter(pk=store.pk).exists():
        raise PermissionDenied('Entre com uma conta ativa com acesso à unidade.')


def can_operate(user, session):
    return session.opened_by_id == user.pk or user.has_perm('sales.manage_cash')


def cash_value(value, *, zero=False):
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0 or (not zero and value == 0) or value != value.quantize(Decimal('0.01')):
        raise ValidationError({'amount': 'Informe um valor válido com até duas casas decimais.'})


def _account(store, account_id):
    account = FinancialAccount.objects.select_for_update(of=('self',)).filter(pk=account_id, store=store).first()
    if account is None:
        raise ValidationError('Conta não encontrada nesta unidade.')
    return account


def _session(store, session_id):
    candidate = CashSession.objects.filter(pk=session_id, account__store=store).first()
    if candidate is None:
        raise ValidationError('Caixa não encontrado nesta unidade.')
    _account(store, candidate.account_id)
    return CashSession.objects.select_for_update(of=('self',)).get(pk=candidate.pk)


def open_cash(*, user, store, account_id, amount, note, request_id):
    user = require_finance(user, 'add_cashsession')
    authorized(user, store); cash_value(amount, zero=True)
    with transaction.atomic():
        account = _account(store, account_id)
        previous = CashSession.objects.filter(opening_request=request_id).first()
        if previous:
            if (previous.account_id, previous.opened_by_id, previous.opening_amount, previous.opening_note) != (account.pk, user.pk, amount, note):
                raise ValidationError('O identificador já foi usado em outra abertura.')
            return previous
        if not account.is_active or not account.cash_box:
            raise ValidationError('Selecione uma conta ativa de caixa físico.')
        if CashSession.objects.filter(account=account, closed_at__isnull=True).exists():
            raise ValidationError('Esta conta já tem um caixa aberto. Consulte o responsável ou feche a abertura atual.')
        try:
            with transaction.atomic():
                return CashSession.objects.create(account=account, opened_by=user, opening_amount=amount, opening_note=note, opening_request=request_id)
        except IntegrityError as error:
            raise ValidationError('Já existe uma abertura ou operação com esse identificador. Atualize a tela.') from error


def move_cash(*, user, store, session_id, kind, amount, reason, request_id):
    user = require_finance(user, 'move_cash')
    authorized(user, store); cash_value(amount)
    if kind not in ('supply', 'withdrawal') or not reason.strip():
        raise ValidationError('Selecione suprimento ou retirada e informe um motivo.')
    signed = amount if kind == 'supply' else -amount
    with transaction.atomic():
        session = _session(store, session_id)
        if not can_operate(user, session):
            raise PermissionDenied('Somente o responsável ou uma pessoa com permissão de caixa pode fazer esta operação.')
        previous = CashPosting.objects.filter(request_id=request_id).first()
        if previous:
            if (previous.session_id, previous.created_by_id, previous.kind, previous.amount, previous.reason) != (session.pk, user.pk, kind, signed, reason):
                raise ValidationError('O identificador já foi usado em outro movimento.')
            return previous
        if session.closed_at:
            raise ValidationError('O caixa está fechado. Abra um novo caixa para movimentar dinheiro.')
        if signed + session.expected_cash < 0:
            raise ValidationError({'amount': 'A retirada ultrapassa o dinheiro previsto no caixa.'})
        try:
            with transaction.atomic():
                return CashPosting.objects.create(session=session, kind=kind, amount=signed, reason=reason, created_by=user, request_id=request_id)
        except IntegrityError as error:
            raise ValidationError('O identificador já foi usado em outra operação.') from error


def close_cash(*, user, store, session_id, counted_amount, note, request_id):
    user = require_finance(user, 'close_cash')
    authorized(user, store); cash_value(counted_amount, zero=True)
    with transaction.atomic():
        session = _session(store, session_id)
        if not can_operate(user, session):
            raise PermissionDenied('Somente o responsável ou uma pessoa com permissão de caixa pode fechar esta abertura.')
        if session.closed_at:
            if (session.closing_request, session.closed_by_id, session.counted_amount, session.closing_note) == (request_id, user.pk, counted_amount, note):
                return session
            raise ValidationError('Este caixa já foi fechado. O fechamento não pode ser substituído.')
        expected = session.expected_cash
        if counted_amount != expected and not note.strip():
            raise ValidationError({'note': 'Informe a justificativa da diferença entre o previsto e o contado.'})
        session.counted_amount = counted_amount
        session.closing_expected = expected
        session.closed_by = user
        session.closed_at = timezone.now()
        session.closing_note = note
        session.closing_request = request_id
        try:
            with transaction.atomic():
                session.save(_allow_close=True)
        except IntegrityError as error:
            raise ValidationError('O identificador já foi usado em outro fechamento.') from error
        return session


def attach_cash_entry(entry, save_entry):
    # Executado na mesma transação do lançamento financeiro. A mesma conta é
    # bloqueada na abertura, no fechamento e em todos os movimentos do caixa.
    if entry.method.kind != 'cash':
        return save_entry()
    with transaction.atomic():
        account = FinancialAccount.objects.select_for_update(of=('self',)).get(pk=entry.account_id)
        session = CashSession.objects.select_for_update(of=('self',)).filter(account=account, closed_at__isnull=True).first()
        if session is None and CashSession.objects.filter(account=account).exists():
            raise ValidationError('Esta conta exige caixa aberto para receber ou estornar dinheiro. Abra o caixa antes de continuar.')
        if session and session.expected_cash + entry.amount < 0:
            raise ValidationError('O caixa não tem dinheiro previsto suficiente para o estorno. Registre um suprimento e tente novamente.')
        result = save_entry()
        if session:
            CashPosting.objects.create(session=session, kind='receipt' if entry.amount > 0 else 'refund', amount=entry.amount, reason=entry.reason, created_by=entry.created_by, financial_entry=entry)
        return result


def post_payable_cash(*, user, store, account, method, amount, reason, request_id):
    """Na transação do título: dinheiro sai/retorna no caixa aberto atual."""
    authorized(user, store)
    if account.store_id != store.pk or method.store_id != store.pk:
        raise ValidationError('A conta e a forma devem pertencer à unidade.')
    if method.kind != 'cash':
        if account.cash_box:
            raise ValidationError('Selecione uma conta bancária para uma saída sem dinheiro físico.')
        return None
    user = require_finance(user, 'move_cash')
    account = _account(store, account.pk)
    if not account.is_active or not account.cash_box:
        raise ValidationError('Selecione uma conta ativa de caixa físico para dinheiro.')
    session = CashSession.objects.select_for_update(of=('self',)).filter(account=account, closed_at__isnull=True).first()
    if session is None:
        raise ValidationError('Abra o caixa antes de registrar pagamento ou estorno a fornecedor em dinheiro.')
    if not can_operate(user, session):
        raise PermissionDenied('Somente o responsável ou uma pessoa com permissão de caixa pode movimentar dinheiro.')
    if session.expected_cash - amount < 0:
        raise ValidationError('O pagamento ultrapassa o dinheiro previsto no caixa. Confira o saldo ou registre um suprimento.')
    if CashPosting.objects.filter(request_id=request_id).exists():
        raise ValidationError('O identificador já pertence a uma movimentação de caixa.')
    return CashPosting.objects.create(session=session, kind='withdrawal' if amount > 0 else 'supply', amount=-amount, reason=reason, created_by=user, request_id=request_id)
