from django.core.exceptions import ValidationError
from django.db import models


class Company(models.Model):
    name = models.CharField("Nome da empresa", max_length=150)
    is_active = models.BooleanField("Ativa", default=True)
    created_at = models.DateTimeField("Criada em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizada em", auto_now=True)

    singleton = models.BooleanField(default=True, unique=True, editable=False)

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


class Customer(models.Model):
    store = models.ForeignKey(
        Store,
        on_delete=models.PROTECT,
        related_name="customers",
        verbose_name="Loja",
    )
    name = models.CharField("Nome completo", max_length=150)
    cpf = models.CharField("CPF", max_length=14, blank=True, null=True)
    birth_date = models.DateField("Data de nascimento", blank=True, null=True)
    phone = models.CharField("Telefone", max_length=30, blank=True)
    email = models.EmailField("E-mail", blank=True)
    notes = models.TextField("Observações", blank=True)
    is_active = models.BooleanField("Ativo", default=True)
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["store", "cpf"],
                condition=models.Q(cpf__isnull=False) & ~models.Q(cpf=""),
                name="unique_customer_cpf_per_store",
            ),
        ]

    def clean(self):
        super().clean()
        self.name = self.name.strip()
        if not self.name:
            raise ValidationError({"name": "Informe o nome do cliente."})

        if self.cpf:
            self.cpf = "".join(char for char in self.cpf if char.isdigit())
            if len(self.cpf) != 11:
                raise ValidationError({"cpf": "Informe um CPF com 11 dígitos."})

    def __str__(self):
        return self.name
