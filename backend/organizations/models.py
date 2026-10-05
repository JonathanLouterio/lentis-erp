from django.db import models

from django.core.exceptions import ValidationError

class Company(models.Model):
    name = models.CharField("Nome da empresa", max_length=150)
    is_active = models.BooleanField("Ativa", default=True)
    created_at = models.DateTimeField("Criada em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizada em", auto_now=True)

    singleton = models.BooleanField(
        default=True,
        unique=True,
        editable=False,
    )

    class Meta:
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(singleton=True),
                name="company_singleton_true",
            ),
        ]

    def clean(self):
        super().clean()

        if Company.objects.exclude(pk=self.pk).exists():
            raise ValidationError(
                "Já existe uma empresa cadastrada. Edite a empresa existente."
            )

    def __str__(self):
        return self.name


class Store(models.Model):
    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="stores",
        verbose_name="Empresa",
    )
    code = models.CharField("Código", max_length=10, unique=True)
    name = models.CharField("Nome da loja", max_length=150)
    phone = models.CharField("Telefone", max_length=30, blank=True)
    email = models.EmailField("E-mail", blank=True)
    is_active = models.BooleanField("Ativa", default=True)
    created_at = models.DateTimeField("Criada em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizada em", auto_now=True)

    class Meta:
        verbose_name = "Loja"
        verbose_name_plural = "Lojas"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"