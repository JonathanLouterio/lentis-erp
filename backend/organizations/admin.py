from django.contrib import admin

from .models import Company, Customer, Store

from .models import Company, Customer, Product, Store


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    readonly_fields = ("created_at", "updated_at")

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not Company.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "company", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")
    list_select_related = ("company",)
    readonly_fields = ("created_at", "updated_at")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "person_type",
        "cpf",
        "cnpj",
        "store",
        "is_active",
    )
    list_filter = ("person_type", "store", "is_active")
    search_fields = (
        "name",
        "trade_name",
        "cpf",
        "cnpj",
        "phone",
        "whatsapp",
        "email",
    )
    list_select_related = ("store",)
    autocomplete_fields = ("store",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            "Identificação",
            {
                "fields": (
                    "store",
                    "person_type",
                    "name",
                    "trade_name",
                    "cpf",
                    "cnpj",
                    "rg",
                    "state_registration",
                    "birth_date",
                )
            },
        ),
        (
            "Contato",
            {
                "fields": (
                    "phone",
                    "whatsapp",
                    "email",
                )
            },
        ),
        (
            "Endereço",
            {
                "fields": (
                    "zip_code",
                    "street",
                    "address_number",
                    "address_complement",
                    "neighborhood",
                    "city",
                    "state",
                )
            },
        ),
        (
            "Controle",
            {
                "fields": (
                    "notes",
                    "is_active",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "internal_code",
        "name",
        "store",
        "category",
        "sale_price",
        "stock_quantity",
        "minimum_stock",
        "is_active",
    )
    list_filter = ("store", "category", "is_active")
    search_fields = (
        "internal_code",
        "barcode",
        "name",
        "brand",
    )
    autocomplete_fields = ("store",)
    list_select_related = ("store",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            "Identificação",
            {
                "fields": (
                    "store",
                    "internal_code",
                    "barcode",
                    "name",
                    "brand",
                    "category",
                )
            },
        ),
        (
            "Valores e estoque",
            {
                "fields": (
                    "cost_price",
                    "sale_price",
                    "stock_quantity",
                    "minimum_stock",
                )
            },
        ),
        (
            "Controle",
            {
                "fields": (
                    "is_active",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def has_delete_permission(self, request, obj=None):
        return False