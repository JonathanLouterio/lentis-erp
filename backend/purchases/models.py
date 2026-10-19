from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class ProtectedRecord(models.Model):
    class Meta:
        abstract=True

    def save(self,*args,_service=False,**kwargs):
        if not _service:raise ValidationError('Use o serviço de compras para preservar entrada, versão e histórico.')
        self.full_clean()
        return super().save(*args,**kwargs)

    def delete(self,*args,**kwargs):
        raise ValidationError('Registros de compra não podem ser excluídos. Cancele apenas os rascunhos.')


class Purchase(ProtectedRecord):
    class Status(models.TextChoices):
        DRAFT='draft','Rascunho'
        RECEIVED='received','Entrada confirmada'
        CANCELLED='cancelled','Cancelada'

    store=models.ForeignKey('organizations.Store',on_delete=models.PROTECT,related_name='purchases',verbose_name='Unidade')
    supplier=models.ForeignKey('organizations.Supplier',on_delete=models.PROTECT,related_name='purchases',verbose_name='Fornecedor')
    reference=models.CharField('Referência do documento',max_length=60,blank=True)
    document_date=models.DateField('Data do documento',null=True,blank=True)
    notes=models.TextField('Observações',max_length=4000,blank=True)
    status=models.CharField(max_length=12,choices=Status.choices,default=Status.DRAFT)
    version=models.PositiveIntegerField(default=1,editable=False)
    supplier_snapshot=models.JSONField(default=dict,blank=True,editable=False)
    updates_cost=models.BooleanField(default=False,editable=False)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='+')
    updated_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='+')
    received_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='+',null=True,blank=True)
    received_at=models.DateTimeField(null=True,blank=True,editable=False)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name='Compra'
        verbose_name_plural='Compras'
        ordering=['-pk']
        permissions=[('receive_purchase','Confirmar entrada de compra')]
        constraints=[
            models.UniqueConstraint(fields=['store','supplier','reference'],condition=~models.Q(reference='') & models.Q(status__in=['draft','received']),name='unique_purchase_supplier_reference'),
            models.CheckConstraint(condition=models.Q(version__gte=1),name='purchase_version_positive'),
            models.CheckConstraint(condition=(models.Q(status='received',received_at__isnull=False,received_by__isnull=False)|models.Q(status__in=['draft','cancelled'],received_at__isnull=True,received_by__isnull=True)),name='purchase_receipt_status_valid'),
        ]

    def clean(self):
        self.reference=self.reference.strip().upper()
        if self.supplier_id and self.supplier.store_id!=self.store_id:raise ValidationError({'supplier':'O fornecedor deve pertencer à unidade da compra.'})

    @property
    def total(self):return sum((item.total for item in self.items.all()),Decimal('0.00'))

    def save(self,*args,_service=False,**kwargs):
        if self.pk:
            previous=type(self).objects.get(pk=self.pk)
            if previous.status!='draft':raise ValidationError('Uma compra confirmada ou cancelada não pode ser alterada.')
            if self.store_id!=previous.store_id or self.created_by_id!=previous.created_by_id:raise ValidationError('A unidade e o autor da compra não podem mudar.')
        return super().save(*args,_service=_service,**kwargs)

    def __str__(self):return f'Compra #{self.pk or "nova"} — {self.get_status_display()}'


class PurchaseItem(ProtectedRecord):
    purchase=models.ForeignKey(Purchase,on_delete=models.PROTECT,related_name='items')
    product=models.ForeignKey('organizations.Product',on_delete=models.PROTECT,related_name='purchase_items')
    product_code=models.CharField(max_length=30)
    product_name=models.CharField(max_length=180)
    quantity=models.DecimalField(max_digits=12,decimal_places=3,validators=[MinValueValidator(Decimal('0.001'))])
    unit_cost=models.DecimalField(max_digits=12,decimal_places=2,validators=[MinValueValidator(Decimal('0'))])

    class Meta:
        ordering=['pk']
        constraints=[models.UniqueConstraint(fields=['purchase','product'],name='unique_product_per_purchase'),models.CheckConstraint(condition=models.Q(quantity__gt=0,unit_cost__gte=0),name='purchase_item_values_valid')]

    @property
    def total(self):return (self.quantity*self.unit_cost).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)

    def clean(self):
        if self.purchase.status!='draft':raise ValidationError('Itens de compra encerrada são somente leitura.')
        if self.product.store_id!=self.purchase.store_id:raise ValidationError('O produto deve pertencer à unidade da compra.')

    def save(self,*args,_service=False,**kwargs):
        if not self._state.adding:raise ValidationError('Os itens são substituídos pelo serviço apenas em rascunho.')
        return super().save(*args,_service=_service,**kwargs)


class PurchaseEvent(ProtectedRecord):
    purchase=models.ForeignKey(Purchase,on_delete=models.PROTECT,related_name='events')
    version=models.PositiveIntegerField()
    action=models.CharField(max_length=12,choices=[('create','Abertura'),('update','Edição'),('receive','Entrada confirmada'),('cancel','Cancelamento')])
    reason=models.CharField(max_length=255,blank=True)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='+')
    created_at=models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering=['-version']
        constraints=[models.UniqueConstraint(fields=['purchase','version'],name='unique_purchase_event_version')]

    def save(self,*args,**kwargs):
        if not self._state.adding:raise ValidationError('Eventos de compra não podem ser alterados.')
        return super().save(*args,**kwargs)


class PurchaseStockMovement(ProtectedRecord):
    item=models.OneToOneField(PurchaseItem,on_delete=models.PROTECT,related_name='stock_link')
    movement=models.OneToOneField('organizations.StockMovement',on_delete=models.PROTECT,related_name='purchase_link')
    class Meta:
        verbose_name='Entrada de estoque da compra'

    def clean(self):
        if self.movement.store_id!=self.item.purchase.store_id or self.movement.product_id!=self.item.product_id or self.movement.movement_type!='entry' or self.movement.quantity!=self.item.quantity:
            raise ValidationError('A movimentação deve corresponder ao item recebido.')

    def save(self,*args,**kwargs):
        if not self._state.adding:raise ValidationError('Entradas de compra não podem ser alteradas.')
        return super().save(*args,**kwargs)


class PurchaseOperation(ProtectedRecord):
    request_id=models.UUIDField(unique=True)
    purchase=models.ForeignKey(Purchase,on_delete=models.PROTECT,related_name='+')
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='+')
    digest=models.CharField(max_length=64)
    created_at=models.DateTimeField(auto_now_add=True)

from .payable_models import PayablePlan, PayableInstallment, PayablePayment  # noqa: E402,F401
