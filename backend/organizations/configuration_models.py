from django.conf import settings
from django.db import models


class ConfigurationEvent(models.Model):
    company = models.ForeignKey('organizations.Company', on_delete=models.PROTECT)
    store = models.ForeignKey('organizations.Store', null=True, blank=True, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=32)
    changes = models.JSONField(default=dict)
    request_id = models.UUIDField(unique=True)
    fingerprint = models.CharField(max_length=64)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        verbose_name = 'Evento de configuração'
        verbose_name_plural = 'Histórico de configurações'
        default_permissions = ()
