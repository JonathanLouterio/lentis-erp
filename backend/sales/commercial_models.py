from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from accounts.models import StoreMembership


class DiscountPolicy(models.Model):
    store = models.ForeignKey('organizations.Store', on_delete=models.PROTECT, related_name='discount_policies', verbose_name='Unidade')
    role = models.CharField('Perfil', max_length=30, choices=StoreMembership.Role.choices)
    limit_percentage = models.DecimalField('Desconto máximo (%)', max_digits=5, decimal_places=2, default=100,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))])

    class Meta:
        verbose_name = 'Limite de desconto por perfil'
        verbose_name_plural = 'Limites de desconto por perfil'
        constraints = [models.UniqueConstraint(fields=['store','role'], name='unique_discount_policy_store_role'),
            models.CheckConstraint(condition=models.Q(limit_percentage__gte=0, limit_percentage__lte=100), name='discount_policy_percentage_valid')]

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.store} — {self.get_role_display()}: {self.limit_percentage}%'


class DiscountAuthorization(models.Model):
    class Action(models.TextChoices):
        REQUEST = 'request', 'Solicitação'
        APPROVE = 'approve', 'Autorização'
        REJECT = 'reject', 'Recusa'

    sale = models.ForeignKey('sales.Sale', on_delete=models.PROTECT, related_name='discount_authorizations', verbose_name='Venda')
    action = models.CharField('Operação', max_length=10, choices=Action.choices)
    request = models.OneToOneField('self', null=True, blank=True, on_delete=models.PROTECT, related_name='decision', verbose_name='Solicitação original')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='discount_actions', verbose_name='Responsável')
    snapshot_hash = models.CharField('Identificador dos valores', max_length=64, editable=False)
    role = models.CharField('Perfil registrado', max_length=30)
    limit_percentage = models.DecimalField('Limite registrado (%)', max_digits=5, decimal_places=2)
    reference_subtotal = models.DecimalField('Subtotal de referência', max_digits=28, decimal_places=2)
    discount_amount = models.DecimalField('Desconto considerado', max_digits=28, decimal_places=2)
    reason = models.CharField('Motivo', max_length=255)
    created_at = models.DateTimeField('Registrado em', auto_now_add=True)

    class Meta:
        verbose_name = 'Registro de autorização de desconto'
        verbose_name_plural = 'Registros de autorização de desconto'
        ordering = ['created_at','pk']
        permissions = [('approve_discount', 'Pode autorizar descontos acima do limite')]
        constraints = [
            models.CheckConstraint(condition=models.Q(action='request', request__isnull=True) | models.Q(action__in=['approve','reject'], request__isnull=False), name='discount_action_request_consistent'),
            models.CheckConstraint(condition=models.Q(reference_subtotal__gte=0, discount_amount__gte=0, limit_percentage__gte=0, limit_percentage__lte=100), name='discount_authorization_values_valid'),
        ]

    def clean(self):
        super().clean()
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValidationError({'reason':'Informe o motivo.'})
        if self.request_id and (self.request.sale_id != self.sale_id or self.request.action != self.Action.REQUEST):
            raise ValidationError('A decisão deve corresponder à solicitação da mesma venda.')

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError('Registros de autorização não podem ser editados.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Registros de autorização não podem ser excluídos.')

    def __str__(self):
        return f'Venda #{self.sale_id} — {self.get_action_display()}'
