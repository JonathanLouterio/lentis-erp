"""Controle do dinheiro físico. Recebimentos bancários permanecem no financeiro."""
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from .payment_models import ImmutableRecord


class CashSession(models.Model):
    account = models.ForeignKey('sales.FinancialAccount', on_delete=models.PROTECT, related_name='cash_sessions', verbose_name='Conta de caixa')
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='cash_sessions_opened', verbose_name='Responsável pela abertura')
    opened_at = models.DateTimeField(auto_now_add=True, verbose_name='Aberto em')
    opening_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)], verbose_name='Dinheiro inicial')
    opening_note = models.CharField(max_length=255, blank=True, verbose_name='Observação da abertura')
    opening_request = models.UUIDField(unique=True, editable=False)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='cash_sessions_closed', verbose_name='Fechado por')
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name='Fechado em')
    counted_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)], verbose_name='Dinheiro contado')
    closing_expected = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, verbose_name='Dinheiro previsto no fechamento')
    closing_note = models.CharField(max_length=255, blank=True, verbose_name='Justificativa do fechamento')
    closing_request = models.UUIDField(unique=True, null=True, blank=True, editable=False)

    class Meta:
        verbose_name = 'Abertura de caixa'
        verbose_name_plural = 'Aberturas de caixa'
        ordering = ['-opened_at', '-pk']
        permissions = [('manage_cash', 'Pode operar e fechar caixas de outros responsáveis'), ('move_cash', 'Pode registrar suprimento e retirada de caixa'), ('close_cash', 'Pode fechar caixa')]
        constraints = [
            models.UniqueConstraint(fields=['account'], condition=models.Q(closed_at__isnull=True), name='one_open_session_per_cash_account'),
            models.CheckConstraint(condition=models.Q(opening_amount__gte=0), name='cash_opening_non_negative'),
            models.CheckConstraint(condition=(models.Q(closed_at__isnull=True, closed_by__isnull=True, counted_amount__isnull=True, closing_expected__isnull=True, closing_request__isnull=True) | models.Q(closed_at__isnull=False, closed_by__isnull=False, counted_amount__isnull=False, counted_amount__gte=0, closing_expected__isnull=False, closing_request__isnull=False)), name='cash_closing_fields_consistent'),
        ]

    @property
    def expected_cash(self):
        if self.closed_at is not None:
            return self.closing_expected
        return self.opening_amount + (self.postings.aggregate(value=models.Sum('amount'))['value'] or Decimal('0'))

    @property
    def difference(self):
        return None if self.closed_at is None else self.counted_amount - self.closing_expected

    def save(self, *args, _allow_close=False, **kwargs):
        if not self._state.adding:
            previous = type(self).objects.get(pk=self.pk)
            fixed = ['account_id', 'opened_by_id', 'opened_at', 'opening_amount', 'opening_note', 'opening_request']
            if previous.closed_at is not None or not _allow_close or any(getattr(previous, key) != getattr(self, key) for key in fixed):
                raise ValidationError('A abertura e o fechamento são históricos e não podem ser editados.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('O histórico do caixa não pode ser excluído.')

    def __str__(self):
        return f'Caixa #{self.pk} — {self.account}'


class CashPosting(ImmutableRecord):
    class Kind(models.TextChoices):
        SUPPLY = 'supply', 'Suprimento'
        WITHDRAWAL = 'withdrawal', 'Sangria / retirada'
        RECEIPT = 'receipt', 'Recebimento em dinheiro'
        REFUND = 'refund', 'Estorno em dinheiro'

    session = models.ForeignKey(CashSession, on_delete=models.PROTECT, related_name='postings', verbose_name='Abertura')
    kind = models.CharField(max_length=12, choices=Kind.choices, verbose_name='Tipo')
    amount = models.DecimalField(max_digits=18, decimal_places=2, verbose_name='Valor lançado')
    reason = models.CharField(max_length=255, verbose_name='Motivo')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name='Operador')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Registrado em')
    financial_entry = models.OneToOneField('sales.FinancialEntry', on_delete=models.PROTECT, null=True, blank=True, related_name='cash_posting', verbose_name='Recebimento / estorno')
    request_id = models.UUIDField(unique=True, null=True, blank=True, editable=False)

    class Meta:
        verbose_name = 'Movimento de caixa'
        verbose_name_plural = 'Movimentos de caixa'
        ordering = ['-created_at', '-pk']
        constraints = [models.CheckConstraint(condition=(
            models.Q(kind='supply', amount__gt=0, financial_entry__isnull=True, request_id__isnull=False) |
            models.Q(kind='withdrawal', amount__lt=0, financial_entry__isnull=True, request_id__isnull=False) |
            models.Q(kind='receipt', amount__gt=0, financial_entry__isnull=False, request_id__isnull=True) |
            models.Q(kind='refund', amount__lt=0, financial_entry__isnull=False, request_id__isnull=True)
        ), name='cash_posting_kind_and_sign_valid')]

    def clean(self):
        super().clean()
        if self.session.closed_at is not None:
            raise ValidationError('Um caixa fechado não aceita novos movimentos.')
        if not self.reason or not self.reason.strip():
            raise ValidationError({'reason': 'Informe o motivo do movimento.'})
        if self.financial_entry_id:
            entry = self.financial_entry
            if entry.account_id != self.session.account_id or entry.method.kind != 'cash' or entry.amount != self.amount or entry.created_by_id != self.created_by_id:
                raise ValidationError('O movimento deve corresponder ao recebimento em dinheiro desta conta.')
