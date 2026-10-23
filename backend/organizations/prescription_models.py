from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


def power(label):
    return models.DecimalField(label, max_digits=6, decimal_places=2, null=True, blank=True)


def distance(label):
    return models.DecimalField(label, max_digits=6, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal('0.01'))])


class Prescription(models.Model):
    store = models.ForeignKey('organizations.Store', on_delete=models.PROTECT, related_name='prescriptions')
    customer = models.ForeignKey('organizations.Customer', on_delete=models.PROTECT, related_name='prescriptions')
    issued_on = models.DateField('Data da receita')
    prescriber_name = models.CharField('Prescritor', max_length=150, blank=True)
    prescriber_registration = models.CharField('Registro do prescritor', max_length=80, blank=True)
    od_sphere = power('OD - Esférico')
    od_cylinder = power('OD - Cilíndrico')
    od_axis = models.PositiveSmallIntegerField('OD - Eixo', null=True, blank=True, validators=[MaxValueValidator(180)])
    od_addition = power('OD - Adição')
    oe_sphere = power('OE - Esférico')
    oe_cylinder = power('OE - Cilíndrico')
    oe_axis = models.PositiveSmallIntegerField('OE - Eixo', null=True, blank=True, validators=[MaxValueValidator(180)])
    oe_addition = power('OE - Adição')
    pd = distance('DP (mm)')
    od_dnp = distance('DNP OD (mm)')
    oe_dnp = distance('DNP OE (mm)')
    notes = models.TextField('Observações', blank=True, max_length=4000)
    version = models.PositiveIntegerField(default=1, editable=False)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Receita oftalmológica'
        verbose_name_plural = 'Receitas oftalmológicas'
        ordering = ['-issued_on', '-pk']
        permissions = [('archive_prescription','Arquivar receita oftalmológica')]
        constraints = [
            models.CheckConstraint(condition=models.Q(version__gte=1), name='prescription_version_positive'),
            models.CheckConstraint(condition=models.Q(od_axis__isnull=True) | models.Q(od_axis__gte=0, od_axis__lte=180), name='prescription_od_axis_valid'),
            models.CheckConstraint(condition=models.Q(oe_axis__isnull=True) | models.Q(oe_axis__gte=0, oe_axis__lte=180), name='prescription_oe_axis_valid'),
        ]

    def clean(self):
        errors = {}
        if self.customer_id and self.customer.store_id != self.store_id:
            errors['customer'] = 'O cliente deve pertencer à unidade selecionada.'
        if not any(getattr(self, f'{eye}_{field}') is not None for eye in ('od','oe') for field in ('sphere','cylinder','addition')):
            errors['od_sphere'] = 'Informe ao menos um valor de esférico, cilíndrico ou adição conforme a receita.'
        for eye in ('od','oe'):
            cylinder, axis = getattr(self, f'{eye}_cylinder'), getattr(self, f'{eye}_axis')
            if cylinder is not None and cylinder != 0 and axis is None:
                errors[f'{eye}_axis'] = 'Informe o eixo indicado na receita para este cilíndrico.'
            if axis is not None and cylinder is None:
                errors[f'{eye}_cylinder'] = 'Informe também o cilíndrico ao registrar o eixo.'
        if errors: raise ValidationError(errors)

    def save(self, *args, _service=False, **kwargs):
        if not _service: raise ValidationError('Use o cadastro de receitas para preservar as revisões e o histórico.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Arquive a receita para preservar o histórico.')

    def __str__(self): return f'Receita #{self.pk} - {self.customer}'


class PrescriptionRevision(models.Model):
    prescription = models.ForeignKey(Prescription, on_delete=models.PROTECT, related_name='revisions')
    version = models.PositiveIntegerField()
    action = models.CharField(max_length=12, choices=[('created','Cadastro'),('updated','Correção'),('archived','Arquivamento')])
    snapshot = models.JSONField()
    reason = models.CharField(max_length=255)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        verbose_name = 'Revisão de receita'
        verbose_name_plural = 'Revisões de receitas'
        ordering = ['-version']
        constraints = [models.UniqueConstraint(fields=['prescription','version'], name='unique_prescription_revision')]
    def save(self, *args, **kwargs):
        if not self._state.adding: raise ValidationError('O histórico de receitas não pode ser alterado.')
        return super().save(*args, **kwargs)
    def delete(self, *args, **kwargs): raise ValidationError('O histórico de receitas não pode ser excluído.')


class PrescriptionOperation(models.Model):
    request_id = models.UUIDField(unique=True)
    prescription = models.ForeignKey(Prescription, on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        verbose_name = 'Operação de receita'
        verbose_name_plural = 'Operações de receitas'
    def save(self, *args, **kwargs):
        if not self._state.adding: raise ValidationError('Operações registradas não podem ser alteradas.')
        return super().save(*args, **kwargs)
    def delete(self, *args, **kwargs): raise ValidationError('Operações registradas não podem ser excluídas.')


CLINICAL_FIELDS = ['issued_on','prescriber_name','prescriber_registration','od_sphere','od_cylinder','od_axis','od_addition','oe_sphere','oe_cylinder','oe_axis','oe_addition','pd','od_dnp','oe_dnp','notes']
