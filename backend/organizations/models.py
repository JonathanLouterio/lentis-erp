from django.core.exceptions import ValidationError
from django.db import models


def _digits(value):
    return "".join(char for char in (value or "") if char.isdigit())


def _has_repeated_digits(value):
    return len(set(value)) == 1


def is_valid_cpf(value):
    cpf = _digits(value)
    if len(cpf) != 11 or _has_repeated_digits(cpf):
        return False

    total = sum(int(cpf[index]) * (10 - index) for index in range(9))
    digit = (total * 10) % 11
    if digit == 10:
        digit = 0
    if digit != int(cpf[9]):
        return False

    total = sum(int(cpf[index]) * (11 - index) for index in range(10))
    digit = (total * 10) % 11
    if digit == 10:
        digit = 0
    return digit == int(cpf[10])


def is_valid_cnpj(value):
    cnpj = _digits(value)
    if len(cnpj) != 14 or _has_repeated_digits(cnpj):
        return False

    first_weights = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
    total = sum(int(value) * weight for value, weight in zip(cnpj[:12], first_weights))
    digit = 0 if total % 11 < 2 else 11 - (total % 11)
    if digit != int(cnpj[12]):
        return False

    second_weights = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
    total = sum(int(value) * weight for value, weight in zip(cnpj[:13], second_weights))
    digit = 0 if total % 11 < 2 else 11 - (total % 11)
    return digit == int(cnpj[13])


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
    code = models.CharField("CÃ³digo", max_length=10, unique=True)
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
    class PersonType(models.TextChoices):
        INDIVIDUAL = "individual", "Pessoa Física"
        COMPANY = "company", "Pessoa Jurídica"

    store = models.ForeignKey(
        Store,
        on_delete=models.PROTECT,
        related_name="customers",
        verbose_name="Loja",
    )
    person_type = models.CharField(
        "Tipo de pessoa",
        max_length=10,
        choices=PersonType.choices,
        default=PersonType.INDIVIDUAL,
    )
    name = models.CharField("Nome completo / RazÃ£o social", max_length=150)
    trade_name = models.CharField("Nome fantasia", max_length=150, blank=True)
    cpf = models.CharField("CPF", max_length=14, blank=True, null=True)
    cnpj = models.CharField("CNPJ", max_length=18, blank=True, null=True)
    rg = models.CharField("RG", max_length=30, blank=True)
    state_registration = models.CharField(
        "Inscrição estadual",
        max_length=30,
        blank=True,
    )
    birth_date = models.DateField("Data de nascimento", blank=True, null=True)
    phone = models.CharField("Telefone", max_length=30, blank=True)
    whatsapp = models.CharField("WhatsApp", max_length=30, blank=True)
    email = models.EmailField("E-mail", blank=True)
    zip_code = models.CharField("CEP", max_length=9, blank=True)
    street = models.CharField("Logradouro", max_length=150, blank=True)
    address_number = models.CharField("Número", max_length=20, blank=True)
    address_complement = models.CharField(
        "Complemento",
        max_length=100,
        blank=True,
    )
    neighborhood = models.CharField("Bairro", max_length=100, blank=True)
    city = models.CharField("Cidade", max_length=100, blank=True)
    state = models.CharField("UF", max_length=2, blank=True)
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
            models.UniqueConstraint(
                fields=["store", "cnpj"],
                condition=models.Q(cnpj__isnull=False) & ~models.Q(cnpj=""),
                name="unique_customer_cnpj_per_store",
            ),
        ]

    def clean(self):
        super().clean()
        self.name = self.name.strip()
        self.cpf = _digits(self.cpf) or None
        self.cnpj = _digits(self.cnpj) or None
        self.state = self.state.strip().upper()

        if not self.name:
            raise ValidationError({"name": "Informe o nome ou razão social."})

        if self.person_type == self.PersonType.INDIVIDUAL:
            if self.cnpj:
                raise ValidationError(
                    {"cnpj": "Pessoa fisica não deve possuir CNPJ."}
                )
            if self.cpf and not is_valid_cpf(self.cpf):
                raise ValidationError({"cpf": "Informe um CPF valido."})
        else:
            if self.cpf:
                raise ValidationError(
                    {"cpf": "Pessoa juridica não deve possuir CPF."}
                )
            if self.cnpj and not is_valid_cnpj(self.cnpj):
                raise ValidationError({"cnpj": "Informe um CNPJ valido."})

        if self.state and len(self.state) != 2:
            raise ValidationError({"state": "Informe a UF com 2 letras."})

    def __str__(self):
        return self.name

    
class Product(models.Model):
    store = models.ForeignKey(
        Store,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name="Loja",
    )
    internal_code = models.CharField(
        "Código interno",
        max_length=30,
        db_index=True,
    )
    barcode = models.CharField(
        "Código de barras",
        max_length=30,
        blank=True,
    )
    name = models.CharField("Descrição", max_length=180)
    brand = models.CharField("Marca", max_length=100, blank=True)
    category = models.CharField("Categoria", max_length=100, blank=True)
    cost_price = models.DecimalField(
        "Preço de custo",
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    sale_price = models.DecimalField(
        "Preço de venda",
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    stock_quantity = models.DecimalField(
        "Estoque atual",
        max_digits=12,
        decimal_places=3,
        default=0,
    )
    minimum_stock = models.DecimalField(
        "Estoque mínimo",
        max_digits=12,
        decimal_places=3,
        default=0,
    )
    is_active = models.BooleanField("Ativo", default=True)
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Produto"
        verbose_name_plural = "Produtos"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["store", "internal_code"],
                name="unique_product_code_per_store",
            ),
            models.UniqueConstraint(
                fields=["store", "barcode"],
                condition=~models.Q(barcode=""),
                name="unique_product_barcode_per_store",
            ),
            models.CheckConstraint(
                condition=models.Q(cost_price__gte=0)
                & models.Q(sale_price__gte=0)
                & models.Q(stock_quantity__gte=0)
                & models.Q(minimum_stock__gte=0),
                name="product_numeric_values_non_negative",
            ),
        ]

    def clean(self):
        super().clean()
        self.internal_code = self.internal_code.strip()
        self.barcode = self.barcode.strip()
        self.name = self.name.strip()

        if not self.internal_code:
            raise ValidationError({"internal_code": "Informe o código interno."})
        if not self.name:
            raise ValidationError({"name": "Informe a descrição do produto."})

        for field in (
            "cost_price",
            "sale_price",
            "stock_quantity",
            "minimum_stock",
        ):
            if getattr(self, field) < 0:
                raise ValidationError({field: "O valor não pode ser negativo."})

    def __str__(self):
        return f"{self.internal_code} - {self.name}"