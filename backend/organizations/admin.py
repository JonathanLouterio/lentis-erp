from django.contrib import admin

from .models import Company, Store


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    readonly_fields = ("created_at", "updated_at")

    def has_add_permission(self, request):
        return (
            super().has_add_permission(request)
            and not Company.objects.exists()
        )

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