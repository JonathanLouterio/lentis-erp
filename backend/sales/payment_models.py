from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models, transaction


class FinancialAccount(models.Model):
    store = models.ForeignKey('organizations.Store', on_delete=models.PROTECT, verbose_name='Unidade')
    code = models.CharField('Código', max_length=30)
    name = models.CharField('Nome', max_length=100)
    is_active = models.BooleanField('Ativa', default=True)

    class Meta:
        verbose_name = 'Conta de recebimento'
        verbose_name_plural = 'Contas de recebimento'
        ordering = ['name', 'pk']
        constraints = [models.UniqueConstraint(fields=['store', 'code'], name='unique_financial_account_store_code')]

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.get(pk=self.pk)
            if previous.store_id != self.store_id:
                raise ValidationError('A conta não pode mudar de unidade.')
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def balance(self):
        return self.entries.aggregate(value=models.Sum('amount'))['value'] or Decimal('0.00')

    def __str__(self):
        return f'{self.store} — {self.name}'


class PaymentMethod(models.Model):
    class Kind(models.TextChoices):
        CASH = 'cash', 'Dinheiro'
        PIX = 'pix', 'Pix'
        TRANSFER = 'transfer', 'Transferência'
        DEBIT = 'debit', 'Cartão de débito'
        CREDIT = 'credit', 'Cartão de crédito'
        STORE_CREDIT = 'store_credit', 'Crediário'
        BOLETO = 'boleto', 'Boleto'

    store = models.ForeignKey('organizations.Store', on_delete=models.PROTECT, verbose_name='Unidade')
    code = models.CharField('Código', max_length=30)
    name = models.CharField('Nome', max_length=100)
    kind = models.CharField('Tipo', max_length=20, choices=Kind.choices)
    is_active = models.BooleanField('Ativa', default=True)

    class Meta:
        verbose_name = 'Forma de pagamento'
        verbose_name_plural = 'Formas de pagamento'
        ordering = ['pk']
        constraints = [models.UniqueConstraint(fields=['store', 'code'], name='unique_payment_method_store_code')]

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.get(pk=self.pk)
            if previous.store_id != self.store_id or previous.kind != self.kind:
                raise ValidationError('A unidade e o tipo da forma de pagamento não podem ser alterados. Crie outra forma.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.store} — {self.name}'


class ImmutableRecord(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError('O registro financeiro é imutável. Use uma operação de estorno.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('O histórico financeiro não pode ser excluído.')


class SalePayment(models.Model):
    sale = models.ForeignKey('sales.Sale', on_delete=models.CASCADE, related_name='payments', verbose_name='Venda')
    method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT, verbose_name='Forma de pagamento')
    account = models.ForeignKey(FinancialAccount, on_delete=models.PROTECT, verbose_name='Conta de recebimento')
    method_name = models.CharField('Forma registrada', max_length=100, editable=False)
    kind = models.CharField('Tipo registrado', max_length=20, choices=PaymentMethod.Kind.choices, editable=False)
    amount = models.DecimalField('Valor', max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    installment_count = models.PositiveSmallIntegerField('Parcelas', default=1, validators=[MinValueValidator(1), MaxValueValidator(12)])
    first_due_date = models.DateField('Primeiro vencimento')
    confirmed = models.BooleanField('Recebimento confirmado', default=False)

    class Meta:
        ordering = ['pk']
        verbose_name = 'Pagamento da venda'
        verbose_name_plural = 'Pagamentos da venda'
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0, installment_count__gte=1, installment_count__lte=12), name='sale_payment_values_valid')]

    def clean(self):
        super().clean()
        if self.method_id and self.method.store_id != self.sale.store_id:
            raise ValidationError({'method': 'A forma de pagamento deve pertencer à unidade da venda.'})
        if self.account_id and self.account.store_id != self.sale.store_id:
            raise ValidationError({'account': 'A conta deve pertencer à unidade da venda.'})
        if self.kind in ('cash', 'pix', 'transfer', 'debit') and self.installment_count != 1:
            raise ValidationError({'installment_count': 'Esta forma aceita uma única parcela.'})
        if self.confirmed and self.kind not in ('cash', 'pix', 'transfer'):
            raise ValidationError({'confirmed': 'Cartão, boleto e crediário são registrados como valores a receber.'})
        if self.amount < Decimal(self.installment_count) / 100:
            raise ValidationError({'amount': 'Cada parcela deve ter pelo menos um centavo.'})

    def save(self, *args, **kwargs):
        from .models import Sale
        with transaction.atomic():
            sale = Sale.objects.select_for_update().get(pk=self.sale_id)
            if sale.status != Sale.Status.DRAFT:
                raise ValidationError('Pagamentos de uma venda finalizada não podem ser editados.')
            self.sale = sale
            if self.pk:
                previous = type(self).objects.get(pk=self.pk)
                if previous.sale_id != self.sale_id:
                    raise ValidationError('O pagamento não pode mudar de venda.')
            self.kind = self.method.kind
            self.method_name = self.method.name
            self.full_clean()
            return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from .models import Sale
        with transaction.atomic():
            if Sale.objects.select_for_update().get(pk=self.sale_id).status != Sale.Status.DRAFT:
                raise ValidationError('Pagamentos finalizados não podem ser excluídos.')
            return super().delete(*args, **kwargs)


class Receivable(ImmutableRecord):
    class Debtor(models.TextChoices):
        CUSTOMER = 'customer', 'Cliente'
        OPERATOR = 'operator', 'Operadora de cartão'

    payment = models.ForeignKey(SalePayment, on_delete=models.PROTECT, related_name='installments', verbose_name='Pagamento')
    number = models.PositiveSmallIntegerField('Parcela')
    due_date = models.DateField('Vencimento')
    amount = models.DecimalField('Valor', max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    debtor = models.CharField('Responsável', max_length=10, choices=Debtor.choices)
    customer_name = models.CharField('Cliente registrado', max_length=180, blank=True)
    created_at = models.DateTimeField('Criada em', auto_now_add=True)

    class Meta:
        ordering = ['due_date', 'pk']
        verbose_name = 'Parcela a receber'
        verbose_name_plural = 'Parcelas a receber'
        constraints = [
            models.UniqueConstraint(fields=['payment', 'number'], name='unique_receivable_payment_number'),
            models.CheckConstraint(condition=models.Q(amount__gt=0, number__gte=1), name='receivable_values_valid'),
        ]

    @property
    def paid_amount(self):
        return self.entries.aggregate(value=models.Sum('amount'))['value'] or Decimal('0.00')

    @property
    def remaining_amount(self):
        if self.payment.sale.status == 'cancelled':
            return Decimal('0.00')
        return self.amount - self.paid_amount

    @property
    def status(self):
        if self.payment.sale.status == 'cancelled':
            return 'cancelled'
        return 'paid' if self.remaining_amount == 0 else 'partial' if self.paid_amount > 0 else 'pending'


class FinancialEntry(ImmutableRecord):
    receivable = models.ForeignKey(Receivable, on_delete=models.PROTECT, related_name='entries', verbose_name='Parcela')
    account = models.ForeignKey(FinancialAccount, on_delete=models.PROTECT, related_name='entries', verbose_name='Conta')
    method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT, verbose_name='Forma de recebimento')
    amount = models.DecimalField('Valor lançado', max_digits=18, decimal_places=2)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name='Registrado por')
    created_at = models.DateTimeField('Registrado em', auto_now_add=True)
    reason = models.CharField('Descrição', max_length=255)
    reversal_of = models.OneToOneField('self', blank=True, null=True, on_delete=models.PROTECT, related_name='reversal', verbose_name='Estorno de')
    request_id = models.UUIDField('Identificador da operação', unique=True, blank=True, null=True, editable=False)

    class Meta:
        ordering = ['-created_at', '-pk']
        verbose_name = 'Lançamento de recebimento'
        verbose_name_plural = 'Lançamentos de recebimento'
        constraints = [models.CheckConstraint(condition=(models.Q(amount__gt=0, reversal_of__isnull=True) | models.Q(amount__lt=0, reversal_of__isnull=False)), name='financial_entry_sign_valid')]

    def clean(self):
        super().clean()
        store_id = self.receivable.payment.sale.store_id
        if self.account.store_id != store_id or self.method.store_id != store_id:
            raise ValidationError('A conta e a forma de recebimento devem pertencer à unidade da venda.')
        if self.reversal_of_id:
            original = self.reversal_of
            if original.reversal_of_id or original.amount != -self.amount or original.account_id != self.account_id or original.receivable_id != self.receivable_id or original.method_id != self.method_id:
                raise ValidationError('O estorno deve corresponder exatamente ao lançamento original.')
        elif self.amount <= 0 or self.amount > self.receivable.remaining_amount:
            raise ValidationError('O recebimento deve ser positivo e não ultrapassar o saldo da parcela.')


class CheckoutRequest(ImmutableRecord):
    request_id = models.UUIDField(unique=True)
    sale = models.ForeignKey('sales.Sale', on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    payload_digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Operação de venda'
        verbose_name_plural = 'Operações de venda'
