from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class ServiceOrder(models.Model):
    class Status(models.TextChoices):
        OPEN = 'open', 'Aberta'
        LAB = 'laboratory', 'No laboratório'
        MOUNTING = 'mounting', 'Em montagem'
        CHECKING = 'checking', 'Em conferência'
        READY = 'ready', 'Pronta para entrega'
        DELIVERED = 'delivered', 'Entregue'
        CANCELLED = 'cancelled', 'Cancelada'

    sale = models.OneToOneField('sales.Sale', on_delete=models.PROTECT, related_name='service_order')
    prescription_record = models.ForeignKey('sales.SalePrescription', null=True, blank=True, on_delete=models.PROTECT, related_name='service_orders')
    snapshot = models.JSONField(default=dict, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    version = models.PositiveIntegerField(default=1)
    promised_on = models.DateField('Previsão de entrega')
    laboratory = models.CharField('Laboratório', max_length=180, blank=True)
    frame_description = models.CharField('Armação / identificação', max_length=255, blank=True)
    lens_description = models.CharField('Lentes / tratamento', max_length=500, blank=True)
    notes = models.TextField('Observações operacionais', blank=True, max_length=4000)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Ordem de serviço'
        verbose_name_plural = 'Ordens de serviço'
        ordering = ['-pk']
        permissions = [('advance_serviceorder','Pode avançar etapas da OS'), ('rework_serviceorder','Pode registrar retrabalho da OS'), ('cancel_serviceorder','Pode cancelar a OS')]
        constraints = [models.CheckConstraint(condition=models.Q(status__in=['open','laboratory','mounting','checking','ready','delivered','cancelled']), name='service_order_status_valid'), models.CheckConstraint(condition=models.Q(version__gte=1), name='service_order_version_positive')]

    def save(self, *args, _service=False, **kwargs):
        if not _service:
            raise ValidationError('Use o serviço de ordens para preservar as etapas e o histórico.')
        if self.prescription_record_id and (self.prescription_record.sale_id != self.sale_id or self.prescription_record.action != 'attached'):
            raise ValidationError('A cópia de receita deve pertencer à venda da OS.')
        if not self._state.adding:
            previous = type(self).objects.get(pk=self.pk)
            if (self.sale_id, self.prescription_record_id, self.snapshot, self.created_by_id) != (previous.sale_id, previous.prescription_record_id, previous.snapshot, previous.created_by_id):
                raise ValidationError('A venda, a receita e os dados de abertura da OS devem ser preservados.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Cancele a ordem para preservar o histórico.')


class ServiceOrderEvent(models.Model):
    order = models.ForeignKey(ServiceOrder, on_delete=models.PROTECT, related_name='events')
    version = models.PositiveIntegerField()
    action = models.CharField(max_length=20)
    from_status = models.CharField(max_length=16, blank=True)
    to_status = models.CharField(max_length=16)
    reason = models.CharField(max_length=1000, blank=True)
    snapshot = models.JSONField(default=dict)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-version']
        constraints = [models.UniqueConstraint(fields=['order','version'], name='unique_service_order_event_version')]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError('O histórico não pode ser alterado.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('O histórico não pode ser excluído.')


class ServiceOrderOperation(models.Model):
    request_id = models.UUIDField(unique=True)
    order = models.ForeignKey(ServiceOrder, on_delete=models.PROTECT, related_name='+')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
