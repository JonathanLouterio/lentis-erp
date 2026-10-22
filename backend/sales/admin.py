from django.contrib import admin
from .models import CheckoutRequest, FinancialAccount, FinancialEntry, PaymentMethod, Receivable, SalePayment


class FinanceSystemAdminMixin:
    """A operação por loja fica na interface do ERP; o admin financeiro é global."""
    def allowed(self,request):
        from organizations.access_permissions import fresh_actor
        user=fresh_actor(request)
        return bool(user and user.is_superuser)
    def has_module_permission(self,request): return self.allowed(request)
    def has_view_permission(self,request,obj=None): return self.allowed(request)
    def has_add_permission(self,request): return self.allowed(request)
    def has_change_permission(self,request,obj=None): return self.allowed(request)
    def has_delete_permission(self,request,obj=None): return self.allowed(request)
    def get_queryset(self,request):
        query=super().get_queryset(request)
        return query if self.allowed(request) else query.none()


@admin.register(FinancialAccount)
class AccountAdmin(FinanceSystemAdminMixin, admin.ModelAdmin):
    @admin.display(description='Dinheiro físico')
    def is_physical_cash(self, obj):
        return obj.cash_box

    list_display = ['name', 'code', 'store', 'is_physical_cash', 'is_active']
    list_filter = ['store', 'is_active']
    search_fields = ['name', 'code']


@admin.register(PaymentMethod)
class MethodAdmin(FinanceSystemAdminMixin, admin.ModelAdmin):
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
class ReceivableAdmin(FinanceSystemAdminMixin, ReadOnlyFinancialAdmin):
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False
    def has_delete_permission(self,request,obj=None): return False

    list_display = ['id', 'payment', 'number', 'due_date', 'amount', 'debtor']
    list_filter = ['debtor', 'due_date', 'payment__sale__store']


@admin.register(FinancialEntry)
class EntryAdmin(FinanceSystemAdminMixin, ReadOnlyFinancialAdmin):
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False
    def has_delete_permission(self,request,obj=None): return False

    list_display = ['id', 'receivable', 'account', 'amount', 'created_by', 'created_at', 'reversal_of']
    list_filter = ['account__store', 'account']


class SaleFinancialHistoryAdmin(FinanceSystemAdminMixin, ReadOnlyFinancialAdmin):
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False
    def has_delete_permission(self,request,obj=None): return False

admin.site.register(SalePayment, SaleFinancialHistoryAdmin)
admin.site.register(CheckoutRequest, SaleFinancialHistoryAdmin)


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


from .models import CashSession, CashPosting


class CashHistoryAdmin(FinanceSystemAdminMixin, ReadOnlyFinancialAdmin):
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False
    def has_delete_permission(self,request,obj=None): return False

    def get_queryset(self, request):
        from accounts.selectors import get_accessible_stores
        query = super().get_queryset(request)
        relation = 'account__store' if self.model is CashSession else 'session__account__store'
        return query.filter(**{relation + '__in': get_accessible_stores(request.user)})


@admin.register(CashSession)
class CashSessionAdmin(CashHistoryAdmin):
    list_display = ['id', 'account', 'opened_by', 'opened_at', 'opening_amount', 'closed_at', 'counted_amount']
    list_filter = ['account__store', 'closed_at']


@admin.register(CashPosting)
class CashPostingAdmin(CashHistoryAdmin):
    list_display = ['id', 'session', 'kind', 'amount', 'created_by', 'created_at']
    list_filter = ['kind', 'session__account__store']


from .models import Quote, QuoteItem, QuoteEvent, QuoteOperation


class QuoteHistoryAdmin(ReadOnlyFinancialAdmin):
    def quote_reader(self,request):
        from organizations.access_permissions import fresh_actor
        actor=fresh_actor(request)
        return bool(actor and actor.has_perm('sales.view_quote'))
    def has_module_permission(self,request):
        return self.quote_reader(request) and super().has_module_permission(request)
    def has_view_permission(self,request,obj=None):
        return self.quote_reader(request) and super().has_view_permission(request,obj)

    def get_queryset(self, request):
        from accounts.selectors import get_accessible_stores
        field = 'store' if self.model is Quote else 'quote__store'
        if not self.quote_reader(request):return super().get_queryset(request).none()
        return super().get_queryset(request).filter(**{field + '__in': get_accessible_stores(request.user)})


@admin.register(Quote)
class QuoteAdmin(QuoteHistoryAdmin):
    list_display = ['id','store','customer','status','valid_until','created_by','sale']
    list_filter = ['store','status']


admin.site.register(QuoteItem, QuoteHistoryAdmin)
admin.site.register(QuoteEvent, QuoteHistoryAdmin)
admin.site.register(QuoteOperation, QuoteHistoryAdmin)
