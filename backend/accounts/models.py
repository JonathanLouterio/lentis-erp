from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Theme(models.TextChoices):
        LIGHT = "light", "Claro"
        DARK = "dark", "Escuro"
        SYSTEM = "system", "Automático"

    theme = models.CharField(
        "Tema",
        max_length=10,
        choices=Theme.choices,
        default=Theme.SYSTEM,
    )


class StoreMembership(models.Model):
    class Role(models.TextChoices):
        MANAGER = "manager", "Gerente"
        SELLER = "seller", "Vendedor"
        CASHIER = "cashier", "Caixa"
        FINANCE = "finance", "Financeiro"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="store_memberships",
        verbose_name="Usuário",
    )
    store = models.ForeignKey(
        "organizations.Store",
        on_delete=models.PROTECT,
        related_name="memberships",
        verbose_name="Loja",
    )
    role = models.CharField(
        "Perfil",
        max_length=20,
        choices=Role.choices,
    )
    is_active = models.BooleanField("Ativo", default=True)
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Vínculo com loja"
        verbose_name_plural = "Vínculos com lojas"
        ordering = ["store__code", "user__username"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "store"],
                name="unique_user_store_membership",
            ),
        ]

    def __str__(self):
        return (
            f"{self.user} - {self.store} "
            f"({self.get_role_display()})"
        )