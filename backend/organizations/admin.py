from django.contrib import admin
from django.db import transaction

from .models import Company, Customer, Product, StockMovement, Store
from accounts.selectors import get_accessible_stores


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
    readonly_fields = ("stock_quantity", "created_at", "updated_at")

    def get_readonly_fields(self, request, obj=None):
        if obj is not None:
            return (*self.readonly_fields, "store")
        return self.readonly_fields

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            if change:
                locked = Product.objects.select_for_update().get(pk=obj.pk)
                obj.stock_quantity = locked.stock_quantity
                obj.store_id = locked.store_id
            else:
                obj.stock_quantity = 0
            super().save_model(request, obj, form, change)

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


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        "created_at", "store", "product", "movement_type", "quantity",
        "balance_before", "balance_after", "created_by",
    )
    list_filter = ("store", "movement_type", "created_at")
    search_fields = ("product__internal_code", "product__name", "reason", "created_by__username")
    list_select_related = ("store", "product", "created_by")
    readonly_fields = (
        "store", "product", "movement_type", "quantity", "quantity_change",
        "balance_before", "balance_after", "reason", "created_by", "created_at",
    )
    fields = readonly_fields
    actions = None

    def get_queryset(self, request):
        return super().get_queryset(request).filter(
            store__in=get_accessible_stores(request.user),
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
