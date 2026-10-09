from django.contrib import admin
from .models import CheckoutRequest, FinancialAccount, FinancialEntry, PaymentMethod, Receivable, SalePayment


@admin.register(FinancialAccount)
class AccountAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'store', 'is_active']
    list_filter = ['store', 'is_active']
    search_fields = ['name', 'code']


@admin.register(PaymentMethod)
class MethodAdmin(admin.ModelAdmin):
    @admin.display(description='Limite de parcelas')
    def effective_installment_limit(self, obj):
        return obj.installment_limit

    list_display = ['name', 'kind', 'store', 'effective_installment_limit', 'is_active']
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


from .models import DiscountPolicy, DiscountAuthorization


@admin.register(DiscountPolicy)
class DiscountPolicyAdmin(admin.ModelAdmin):
    list_display = ['store','role','limit_percentage']
    list_filter = ['store','role']

    def get_queryset(self, request):
        from accounts.selectors import get_accessible_stores
        return super().get_queryset(request).filter(store__in=get_accessible_stores(request.user))

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'store':
            from accounts.selectors import get_accessible_stores
            kwargs['queryset'] = get_accessible_stores(request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        from accounts.selectors import get_accessible_stores
        from django.core.exceptions import PermissionDenied
        if not get_accessible_stores(request.user).filter(pk=obj.store_id).exists():
            raise PermissionDenied('Você não possui acesso a esta unidade.')
        super().save_model(request, obj, form, change)


@admin.register(DiscountAuthorization)
class DiscountAuthorizationAdmin(ReadOnlyFinancialAdmin):
    list_display = ['id','sale','action','created_by','discount_amount','limit_percentage','created_at']
    list_filter = ['action','sale__store']
    search_fields = ['reason','created_by__username']

    def get_queryset(self, request):
        from accounts.selectors import get_accessible_stores
        return super().get_queryset(request).filter(sale__store__in=get_accessible_stores(request.user))
