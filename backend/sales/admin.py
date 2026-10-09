from django.contrib import admin
from .models import CheckoutRequest, FinancialAccount, FinancialEntry, PaymentMethod, Receivable, SalePayment


@admin.register(FinancialAccount)
class AccountAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'store', 'is_active']
    list_filter = ['store', 'is_active']
    search_fields = ['name', 'code']


@admin.register(PaymentMethod)
class MethodAdmin(admin.ModelAdmin):
    list_display = ['name', 'kind', 'store', 'is_active']
    list_filter = ['store', 'kind', 'is_active']
    search_fields = ['name', 'code']


class ReadOnlyFinancialAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Receivable)
class ReceivableAdmin(ReadOnlyFinancialAdmin):
    list_display = ['id', 'payment', 'number', 'due_date', 'amount', 'debtor']
    list_filter = ['debtor', 'due_date', 'payment__sale__store']


@admin.register(FinancialEntry)
class EntryAdmin(ReadOnlyFinancialAdmin):
    list_display = ['id', 'receivable', 'account', 'amount', 'created_by', 'created_at', 'reversal_of']
    list_filter = ['account__store', 'account']


admin.site.register(SalePayment, ReadOnlyFinancialAdmin)
admin.site.register(CheckoutRequest, ReadOnlyFinancialAdmin)
