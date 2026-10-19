from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class SalePrescription(models.Model):
    sale = models.ForeignKey('sales.Sale', on_delete=models.PROTECT, related_name='prescription_history')
    customer = models.ForeignKey('organizations.Customer', on_delete=models.PROTECT)
    source = models.ForeignKey('organizations.Prescription', on_delete=models.PROTECT, null=True, blank=True)
    source_version = models.PositiveIntegerField(null=True, blank=True)
    action = models.CharField(max_length=12, choices=[('attached','Receita selecionada'),('removed','Vínculo removido')])
    snapshot = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        verbose_name = 'Receita utilizada na venda'
        verbose_name_plural = 'Receitas utilizadas nas vendas'
        ordering = ['-pk']
        constraints = [models.CheckConstraint(condition=(models.Q(action='attached',source__isnull=False,source_version__isnull=False,source_version__gte=1) | models.Q(action='removed',source__isnull=True,source_version__isnull=True)),name='sale_prescription_source_consistent')]
    def save(self,*args,**kwargs):
        if not self._state.adding:raise ValidationError('A cópia de receita registrada na venda não pode ser alterada.')
        self.full_clean()
        return super().save(*args,**kwargs)
    def delete(self,*args,**kwargs):raise ValidationError('A cópia e o histórico da receita da venda devem ser preservados.')
