"""Títulos de compras e despesas e lançamentos imutáveis; escritas pelo serviço transacional."""
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class PayableRecord(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, _service=False, **kwargs):
        if not _service or not self._state.adding:
            raise ValidationError('O histórico financeiro é imutável. Use as operações de geração, pagamento e estorno.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('O histórico financeiro não pode ser excluído.')


class PayablePlan(PayableRecord):
    class ExpenseCategory(models.TextChoices):
        TRANSPORT = 'transport', 'Transporte / Uber'
        RENT = 'rent', 'Aluguel'
        WATER = 'water', 'Água'
        ELECTRICITY = 'electricity', 'Energia elétrica'
        INTERNET = 'internet', 'Internet / telefone'
        FINANCING = 'financing', 'Financiamento'
        SUPPLIER_BILL = 'supplier_bill', 'Boleto de fornecedor'
        OTHER = 'other', 'Outras despesas'

    purchase = models.OneToOneField('purchases.Purchase', on_delete=models.PROTECT, related_name='payable_plan', null=True, blank=True)
    expense_store = models.ForeignKey('organizations.Store', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    expense_category = models.CharField(max_length=20, choices=ExpenseCategory.choices, blank=True, default='')
    expense_description = models.CharField(max_length=160, blank=True, default='')
    expense_payee = models.CharField(max_length=140, blank=True, default='')
    expense_reference = models.CharField(max_length=120, blank=True, default='')
    total = models.DecimalField(max_digits=18, decimal_places=2)
    installment_count = models.PositiveSmallIntegerField()
    first_due_date = models.DateField()
    interval_unit = models.CharField(max_length=6, choices=[('months', 'Meses'), ('days', 'Dias')])
    interval_count = models.PositiveSmallIntegerField()
    request_id = models.UUIDField(unique=True)
    digest = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Conta a pagar'
        verbose_name_plural = 'Contas a pagar'
        ordering = ['-pk']
        permissions = [('pay_payable', 'Registrar pagamento de conta a pagar'), ('reverse_payable', 'Estornar pagamento de conta a pagar'), ('add_operating_expense', 'Lançar despesa operacional'), ('cancel_operating_expense', 'Cancelar despesa operacional')]
        constraints = [
            models.CheckConstraint(condition=(
                models.Q(purchase__isnull=False, expense_store__isnull=True, expense_category='', expense_description='', expense_payee='', expense_reference='') |
                (models.Q(purchase__isnull=True, expense_store__isnull=False) & ~models.Q(expense_category='') & ~models.Q(expense_description=''))
            ), name='payable_plan_single_source'),
            models.CheckConstraint(condition=models.Q(total__gt=0, installment_count__gte=1, installment_count__lte=12), name='payable_plan_values_valid'),
            models.CheckConstraint(condition=(models.Q(interval_unit='months', interval_count__gte=1, interval_count__lte=12) | models.Q(interval_unit='days', interval_count__gte=1, interval_count__lte=365)), name='payable_plan_interval_valid'),
        ]

    @classmethod
    def for_stores(cls, stores, prefix=''):
        return models.Q(**{f'{prefix}purchase__store__in': stores}) | models.Q(**{f'{prefix}expense_store__in': stores})

    @property
    def store_id(self):
        return self.expense_store_id if self.expense_store_id else self.purchase.store_id

    @property
    def document_label(self):
        return f'Compra #{self.purchase_id}' if self.purchase_id else f'Despesa #{self.pk}'

    @property
    def party_name(self):
        if self.purchase_id:
            return self.purchase.supplier_snapshot.get('name') or self.purchase.supplier.name
        return self.expense_payee or self.expense_description

    def clean(self):
        if self.purchase_id and (self.purchase.status != 'received' or self.total != self.purchase.total):
            raise ValidationError('Gere o título com o total de uma compra recebida.')
        if not self.purchase_id and (not self.expense_store_id or not self.expense_description.strip()):
            raise ValidationError('Informe a unidade e a descrição da despesa.')

    def __str__(self):
        return self.document_label


class ExpenseCancellation(PayableRecord):
    plan = models.OneToOneField(PayablePlan, on_delete=models.PROTECT, related_name='cancellation')
    request_id = models.UUIDField(unique=True)
    digest = models.CharField(max_length=64)
    reason = models.CharField(max_length=255)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)


class PayableInstallment(PayableRecord):
    plan = models.ForeignKey(PayablePlan, on_delete=models.PROTECT, related_name='installments')
    number = models.PositiveSmallIntegerField()
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=18, decimal_places=2)

    class Meta:
        ordering = ['number']
        constraints = [
            models.UniqueConstraint(fields=['plan', 'number'], name='unique_payable_installment'),
            models.CheckConstraint(condition=models.Q(amount__gt=0, number__gte=1, number__lte=12), name='payable_installment_values_valid'),
        ]

    @property
    def paid(self):
        return self.payments.aggregate(value=models.Sum('amount'))['value'] or Decimal('0.00')

    @property
    def remaining(self):
        return self.amount - self.paid


class PayablePayment(PayableRecord):
    installment = models.ForeignKey(PayableInstallment, on_delete=models.PROTECT, related_name='payments')
    account = models.ForeignKey('sales.FinancialAccount', on_delete=models.PROTECT, related_name='payable_payments')
    method = models.ForeignKey('sales.PaymentMethod', on_delete=models.PROTECT, related_name='payable_payments')
    account_name = models.CharField(max_length=100)
    method_name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    paid_on = models.DateField()
    reason = models.CharField(max_length=255)
    reversal_of = models.OneToOneField('self', on_delete=models.PROTECT, null=True, blank=True, related_name='reversal')
    cash_posting = models.OneToOneField('sales.CashPosting', on_delete=models.PROTECT, null=True, blank=True, related_name='payable_payment')
    request_id = models.UUIDField(unique=True)
    digest = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Pagamento de conta a pagar'
        verbose_name_plural = 'Pagamentos de contas a pagar'
        ordering = ['-pk']
        constraints = [models.CheckConstraint(condition=(models.Q(amount__gt=0, reversal_of__isnull=True) | models.Q(amount__lt=0, reversal_of__isnull=False)), name='payable_payment_sign_valid')]

    def clean(self):
        store_id = self.installment.plan.store_id
        if self.account.store_id != store_id or self.method.store_id != store_id:
            raise ValidationError('A conta e a forma devem pertencer à unidade do título.')
        if not self.reason.strip():
            raise ValidationError({'reason': 'Informe a referência ou justificativa.'})
        if self.reversal_of_id:
            original = self.reversal_of
            if original.reversal_of_id or (original.installment_id, original.account_id, original.method_id, -original.amount) != (self.installment_id, self.account_id, self.method_id, self.amount):
                raise ValidationError('O estorno deve corresponder integralmente ao pagamento original.')
        if self.cash_posting_id and (self.cash_posting.session.account_id != self.account_id or self.cash_posting.amount != -self.amount or self.cash_posting.created_by_id != self.created_by_id):
            raise ValidationError('A movimentação de caixa deve corresponder ao pagamento.')
