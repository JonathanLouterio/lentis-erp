from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction


ZERO = Decimal("0.00")
CENT = Decimal("0.01")


class Sale(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        COMPLETED = "completed", "Finalizada"
        CANCELLED = "cancelled", "Cancelada"

    store = models.ForeignKey(
        "organizations.Store", on_delete=models.PROTECT,
        related_name="sales", verbose_name="Unidade",
    )
    customer = models.ForeignKey(
        "organizations.Customer", on_delete=models.PROTECT,
        related_name="sales", verbose_name="Cliente", blank=True, null=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="sales_created", verbose_name="Criada por", editable=False,
    )
    status = models.CharField(
        "Situação", max_length=12, choices=Status.choices,
        default=Status.DRAFT, editable=False,
    )
    discount_amount = models.DecimalField("Desconto da venda (R$)", max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(ZERO)])
    notes = models.TextField("Observações", blank=True)
    created_at = models.DateTimeField("Criada em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizada em", auto_now=True)
    completed_at = models.DateTimeField("Finalizada em", blank=True, null=True, editable=False)
    cancelled_at = models.DateTimeField("Cancelada em", blank=True, null=True, editable=False)
    cancellation_reason = models.CharField("Motivo do cancelamento", max_length=255, blank=True, editable=False)

    class Meta:
        verbose_name = "Venda"
        verbose_name_plural = "Vendas"
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.CheckConstraint(condition=models.Q(discount_amount__gte=0), name="sale_discount_nonnegative"),
            models.CheckConstraint(
                condition=(
                    models.Q(status="draft", completed_at__isnull=True, cancelled_at__isnull=True, cancellation_reason="")
                    | models.Q(status="completed", completed_at__isnull=False, cancelled_at__isnull=True, cancellation_reason="")
                    | (models.Q(status="cancelled", cancelled_at__isnull=False) & ~models.Q(cancellation_reason=""))
                ),
                name="sale_status_dates_consistent",
            ),
        ]

    def clean(self):
        super().clean()
        self.cancellation_reason = self.cancellation_reason.strip()
        if self.discount_amount < 0 or (self.pk and self.total < 0):
            raise ValidationError({"discount_amount": "O desconto não pode ultrapassar o valor dos itens."})
        if self.customer_id and self.store_id and self.customer.store_id != self.store_id:
            raise ValidationError({"customer": "O cliente deve pertencer à unidade da venda."})
        if self.status == self.Status.DRAFT:
            if self.store_id and (not self.store.is_active or not self.store.company.is_active):
                raise ValidationError({"store": "Selecione uma unidade ativa."})
            if self.customer_id and not self.customer.is_active:
                raise ValidationError({"customer": "Selecione um cliente ativo."})

    def calculate_totals(self):
        subtotal = ZERO
        discount = self.discount_amount
        if self.pk:
            for item in self.items.all():
                subtotal += item.subtotal
                discount += item.discount_amount
        return {"subtotal": subtotal, "discount_total": discount, "total": subtotal - discount}

    @property
    def subtotal(self):
        return self.calculate_totals()["subtotal"]

    @property
    def discount_total(self):
        return self.calculate_totals()["discount_total"]

    @property
    def total(self):
        return self.calculate_totals()["total"]

    def save(self, *args, _allow_status_change=False, **kwargs):
        # As transições serão chamadas pelo serviço de finalização/cancelamento,
        # na mesma transação das movimentações. Uma edição comum não as executa.
        with transaction.atomic():
            if not self._state.adding:
                previous = Sale.objects.select_for_update().get(pk=self.pk)
                if self.store_id != previous.store_id or self.created_by_id != previous.created_by_id:
                    raise ValidationError("A unidade e o autor da venda não podem ser alterados.")
                if not _allow_status_change and (
                    previous.status != self.Status.DRAFT or self.status != previous.status
                ):
                    raise ValidationError("Use o serviço de vendas para finalizar ou cancelar uma venda.")
            elif self.status != self.Status.DRAFT:
                raise ValidationError("Uma venda deve ser criada como rascunho.")
            self.full_clean()
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            current = Sale.objects.select_for_update().get(pk=self.pk)
            if current.status != self.Status.DRAFT:
                raise ValidationError("Somente rascunhos podem ser excluídos. Use o cancelamento para vendas finalizadas.")
            return super().delete(*args, **kwargs)

    def __str__(self):
        return f"Venda #{self.pk or 'nova'} — {self.get_status_display()}"


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items", verbose_name="Venda")
    product = models.ForeignKey(
        "organizations.Product", on_delete=models.PROTECT,
        related_name="sale_items", verbose_name="Produto",
    )
    product_code = models.CharField("Código registrado", max_length=30, blank=True, default="", editable=False)
    product_name = models.CharField("Descrição registrada", max_length=180, blank=True, default="", editable=False)
    quantity = models.DecimalField(
        "Quantidade", max_digits=12, decimal_places=3, default=1,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    unit_price = models.DecimalField(
        "Preço unitário", max_digits=12, decimal_places=2,
        validators=[MinValueValidator(ZERO)],
    )
    reference_price = models.DecimalField("Preço de referência", max_digits=12, decimal_places=2, null=True, blank=True, editable=False, validators=[MinValueValidator(ZERO)])
    discount_amount = models.DecimalField(
        "Desconto do item (R$)", max_digits=12, decimal_places=2,
        default=0, validators=[MinValueValidator(ZERO)],
    )
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Item da venda"
        verbose_name_plural = "Itens da venda"
        ordering = ["pk"]
        constraints = [
            models.CheckConstraint(condition=models.Q(reference_price__isnull=True) | models.Q(reference_price__gte=0), name="sale_item_reference_price_valid"),
            models.UniqueConstraint(fields=["sale", "product"], name="unique_product_per_sale"),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0) & models.Q(unit_price__gte=0) & models.Q(discount_amount__gte=0),
                name="sale_item_values_valid",
            ),
        ]

    @property
    def subtotal(self):
        return (self.quantity * self.unit_price).quantize(CENT, rounding=ROUND_HALF_UP)

    @property
    def total(self):
        return self.subtotal - self.discount_amount

    def clean(self):
        super().clean()
        if self.sale_id and self.product_id:
            if self.product.store_id != self.sale.store_id:
                raise ValidationError({"product": "O produto deve pertencer à unidade da venda."})
            if self.sale.status != Sale.Status.DRAFT:
                raise ValidationError("Os itens de uma venda finalizada ou cancelada não podem ser alterados.")
            if not self.product.is_active:
                raise ValidationError({"product": "Selecione um produto ativo."})
        if all(isinstance(value, Decimal) and value.is_finite() for value in (
            self.quantity, self.unit_price, self.discount_amount,
        )) and self.discount_amount > self.subtotal:
            raise ValidationError({"discount_amount": "O desconto não pode superar o subtotal do item."})

    def save(self, *args, **kwargs):
        with transaction.atomic():
            sale = Sale.objects.select_for_update().get(pk=self.sale_id)
            if sale.status != Sale.Status.DRAFT:
                raise ValidationError("Somente itens de rascunhos podem ser alterados.")
            previous = None if self._state.adding else SaleItem.objects.get(pk=self.pk)
            if previous and previous.sale_id != self.sale_id:
                raise ValidationError("Um item não pode ser transferido para outra venda.")
            self.sale = sale
            if previous is None or previous.product_id != self.product_id:
                self.reference_price = self.product.sale_price
                self.product_code = self.product.internal_code
                self.product_name = self.product.name
                if self.unit_price is None:
                    self.unit_price = self.product.sale_price
                if kwargs.get("update_fields") is not None:
                    kwargs["update_fields"] = set(kwargs["update_fields"]) | {"product_code", "product_name", "unit_price", "reference_price"}
            self.full_clean()
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            current = SaleItem.objects.get(pk=self.pk)
            sale = Sale.objects.select_for_update().get(pk=current.sale_id)
            if sale.status != Sale.Status.DRAFT:
                raise ValidationError("Somente itens de rascunhos podem ser excluídos.")
            return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.product_code} — {self.product_name}"


class SaleEvent(models.Model):
    class EventType(models.TextChoices):
        COMPLETED = "completed", "Finalização"
        CANCELLED = "cancelled", "Cancelamento"

    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="events", verbose_name="Venda")
    event_type = models.CharField("Operação", max_length=12, choices=EventType.choices)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="sale_events", verbose_name="Responsável",
    )
    reason = models.CharField("Motivo", max_length=255, blank=True)
    created_at = models.DateTimeField("Registrado em", auto_now_add=True)

    class Meta:
        verbose_name = "Evento da venda"
        verbose_name_plural = "Eventos das vendas"
        ordering = ["created_at", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["sale", "event_type"], name="unique_event_type_per_sale"),
            models.CheckConstraint(
                condition=models.Q(event_type="completed") | (models.Q(event_type="cancelled") & ~models.Q(reason="")),
                name="sale_event_type_reason_valid",
            ),
        ]

    def clean(self):
        super().clean()
        self.reason = self.reason.strip()
        if self.event_type == self.EventType.CANCELLED and not self.reason:
            raise ValidationError({"reason": "Informe o motivo do cancelamento."})

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Eventos registrados não podem ser editados.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Eventos registrados não podem ser excluídos.")

    def __str__(self):
        return f"Venda #{self.sale_id} — {self.get_event_type_display()}"


class SaleStockMovement(models.Model):
    event = models.ForeignKey(SaleEvent, on_delete=models.PROTECT, related_name="stock_movements", verbose_name="Evento")
    item = models.ForeignKey(SaleItem, on_delete=models.PROTECT, related_name="stock_movements", verbose_name="Item")
    movement = models.OneToOneField(
        "organizations.StockMovement", on_delete=models.PROTECT,
        related_name="sale_link", verbose_name="Movimentação",
    )

    class Meta:
        verbose_name = "Movimentação da venda"
        verbose_name_plural = "Movimentações das vendas"
        constraints = [
            models.UniqueConstraint(fields=["event", "item"], name="unique_stock_movement_per_event_item"),
        ]

    def clean(self):
        super().clean()
        if self.event.sale_id != self.item.sale_id:
            raise ValidationError("O evento e o item devem pertencer à mesma venda.")
        if self.movement.store_id != self.item.sale.store_id or self.movement.product_id != self.item.product_id:
            raise ValidationError("A movimentação deve corresponder ao produto e à unidade do item.")
        expected_type = "exit" if self.event.event_type == SaleEvent.EventType.COMPLETED else "entry"
        if self.movement.movement_type != expected_type or self.movement.quantity != self.item.quantity:
            raise ValidationError("A movimentação deve corresponder ao tipo e à quantidade da operação.")

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Vínculos de movimentações não podem ser editados.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Vínculos de movimentações não podem ser excluídos.")

    def __str__(self):
        return f"Venda #{self.item.sale_id} — movimentação #{self.movement_id}"


# Estes modelos pertencem ao mesmo app; o arquivo separado mantém o módulo legível.
from .payment_models import FinancialAccount, PaymentMethod, SalePayment, Receivable, FinancialEntry, CheckoutRequest  # noqa: E402,F401

from .commercial_models import DiscountPolicy, DiscountAuthorization  # noqa: E402,F401
