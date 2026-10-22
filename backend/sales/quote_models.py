from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone
from .payment_models import ImmutableRecord


class Quote(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Rascunho'
        SENT = 'sent', 'Proposta pronta'
        ACCEPTED = 'accepted', 'Aceito'
        REJECTED = 'rejected', 'Recusado'
        CONVERTED = 'converted', 'Convertido em venda'
    store = models.ForeignKey('organizations.Store', on_delete=models.PROTECT, related_name='quotes', verbose_name='Unidade')
    customer = models.ForeignKey('organizations.Customer', null=True, blank=True, on_delete=models.PROTECT, verbose_name='Cliente')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name='Criado por')
    status = models.CharField(max_length=12, choices=Status.choices, default='draft', verbose_name='Situação')
    valid_until = models.DateField(verbose_name='Válido até')
    notes = models.TextField(blank=True, verbose_name='Observações')
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)], verbose_name='Desconto geral')
    version = models.PositiveIntegerField(default=1, editable=False)
    sale = models.OneToOneField('sales.Sale', null=True, blank=True, on_delete=models.PROTECT, related_name='source_quote', verbose_name='Venda gerada')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        permissions = [('send_quote','Pode preparar proposta de orçamento'), ('accept_quote','Pode registrar aceite de orçamento'), ('reject_quote','Pode recusar orçamento'), ('print_quote','Pode imprimir orçamento'), ('convert_quote','Pode converter orçamento em venda')]
        verbose_name = 'Orçamento'
        verbose_name_plural = 'Orçamentos'
        ordering = ['-created_at', '-pk']
        constraints = [
            models.CheckConstraint(condition=models.Q(discount_amount__gte=0, version__gte=1), name='quote_values_valid'),
            models.CheckConstraint(condition=models.Q(status='converted', sale__isnull=False) | (models.Q(status__in=['draft','sent','accepted','rejected'], sale__isnull=True)), name='quote_conversion_consistent'),
        ]
    @property
    def is_expired(self):
        return self.status not in ('converted', 'rejected') and self.valid_until < timezone.localdate(timezone=ZoneInfo('America/Sao_Paulo'))
    @property
    def subtotal(self):
        return sum((item.subtotal for item in self.items.all()), Decimal('0'))
    @property
    def total(self):
        return sum((item.total for item in self.items.all()), Decimal('0')) - self.discount_amount
    def clean(self):
        super().clean()
        if self.customer_id and (self.customer.store_id != self.store_id or not self.customer.is_active):
            raise ValidationError({'customer': 'Selecione um cliente ativo desta unidade.'})
        if self.sale_id and self.sale.store_id != self.store_id:
            raise ValidationError('A venda gerada deve pertencer à unidade do orçamento.')
        if self.pk and self.total < 0:
            raise ValidationError({'discount_amount': 'O desconto geral ultrapassa o total dos itens.'})
    def save(self, *args, _allow_transition=False, **kwargs):
        if self.pk:
            previous = type(self).objects.get(pk=self.pk)
            if previous.status in ('converted', 'rejected'):
                raise ValidationError('Orçamentos convertidos ou recusados preservam o histórico e não podem ser editados.')
            if previous.store_id != self.store_id or previous.created_by_id != self.created_by_id:
                raise ValidationError('O orçamento não pode mudar de unidade ou autor.')
            if (previous.status != self.status or previous.sale_id != self.sale_id) and not _allow_transition:
                raise ValidationError('Use as operações do orçamento para mudar sua situação.')
        self.full_clean()
        return super().save(*args, **kwargs)
    def delete(self, *args, **kwargs):
        raise ValidationError('Recuse o orçamento para preservar o histórico; não exclua o registro.')
    def __str__(self): return f'Orçamento #{self.pk or "novo"}'


class QuoteItem(models.Model):
    quote = models.ForeignKey(Quote, on_delete=models.PROTECT, related_name='items')
    product = models.ForeignKey('organizations.Product', on_delete=models.PROTECT)
    product_name = models.CharField(max_length=180, editable=False)
    product_code = models.CharField(max_length=30, editable=False)
    quantity = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(Decimal('0.001'))])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    class Meta:
        verbose_name = 'Item do orçamento'
        verbose_name_plural = 'Itens do orçamento'
        ordering = ['pk']
        constraints = [models.UniqueConstraint(fields=['quote','product'], name='unique_product_per_quote'), models.CheckConstraint(condition=models.Q(quantity__gt=0, unit_price__gte=0, discount_amount__gte=0), name='quote_item_values_valid')]
    @property
    def subtotal(self): return (self.quantity * self.unit_price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    @property
    def total(self): return self.subtotal - self.discount_amount
    def clean(self):
        super().clean()
        if self.product.store_id != self.quote.store_id or not self.product.is_active:
            raise ValidationError('Selecione um produto ativo da unidade do orçamento.')
        if self.discount_amount > self.subtotal:
            raise ValidationError({'discount_amount': 'O desconto ultrapassa o subtotal do item.'})
    def save(self, *args, **kwargs):
        with transaction.atomic():
            quote = Quote.objects.select_for_update().get(pk=self.quote_id)
            if quote.status != 'draft': raise ValidationError('Edite os itens apenas enquanto o orçamento estiver em rascunho.')
            if self.pk:
                previous = type(self).objects.get(pk=self.pk)
                if previous.quote_id != self.quote_id: raise ValidationError('O item não pode mudar de orçamento.')
            self.quote = quote
            self.product_name = self.product.name; self.product_code = self.product.internal_code
            self.full_clean()
            return super().save(*args, **kwargs)
    def delete(self, *args, **kwargs):
        with transaction.atomic():
            if Quote.objects.select_for_update().get(pk=self.quote_id).status != 'draft':
                raise ValidationError('Itens de um orçamento aprovado, recusado ou convertido não podem ser removidos.')
            return super().delete(*args, **kwargs)


class QuoteEvent(ImmutableRecord):
    quote = models.ForeignKey(Quote, on_delete=models.PROTECT, related_name='events')
    action = models.CharField(max_length=20)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    version = models.PositiveIntegerField()
    class Meta:
        verbose_name = 'Histórico de orçamento'
        verbose_name_plural = 'Históricos de orçamento'
        ordering = ['pk']


class QuoteOperation(ImmutableRecord):
    request_id = models.UUIDField(unique=True)
    quote = models.ForeignKey(Quote, on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        verbose_name = 'Operação de orçamento'
        verbose_name_plural = 'Operações de orçamento'
