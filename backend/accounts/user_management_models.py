from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class UserAccessEvent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                             related_name="access_events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                              related_name="performed_access_events")
    action = models.CharField(max_length=24)
    changes = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        verbose_name = "Histórico de acesso do usuário"
        verbose_name_plural = "Históricos de acesso dos usuários"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("O histórico de acesso não pode ser alterado.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("O histórico de acesso não pode ser excluído.")
