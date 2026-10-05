from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import StoreMembership, User


admin.site.register(User, UserAdmin)


@admin.register(StoreMembership)
class StoreMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "store", "role", "is_active")
    list_filter = ("store", "role", "is_active")
    search_fields = ("user__username", "store__code", "store__name")
    list_select_related = ("user", "store")
    autocomplete_fields = ("user", "store")
    readonly_fields = ("created_at", "updated_at")

    def has_delete_permission(self, request, obj=None):
        return False