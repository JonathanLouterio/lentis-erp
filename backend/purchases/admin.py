from django.contrib import admin
from accounts.selectors import get_accessible_stores
from .models import Purchase


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display=('id','store','supplier','reference','status','received_at')
    list_filter=('store','status')
    search_fields=('reference','supplier__name','supplier__document')
    readonly_fields=tuple(field.name for field in Purchase._meta.fields)
    actions=None

    def get_queryset(self,request):return super().get_queryset(request).filter(store__in=get_accessible_stores(request.user))
    def has_add_permission(self,request):return False
    def has_change_permission(self,request,obj=None):return False
    def has_delete_permission(self,request,obj=None):return False

from .models import PayablePlan, PayablePayment


@admin.register(PayablePlan)
class PayablePlanAdmin(admin.ModelAdmin):
    list_display = ('id', 'purchase', 'total', 'installment_count', 'created_by', 'created_at')
    readonly_fields = tuple(field.name for field in PayablePlan._meta.fields)
    actions = None
    def get_queryset(self, request):
        return super().get_queryset(request).filter(purchase__store__in=get_accessible_stores(request.user))
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(PayablePayment)
class PayablePaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'installment', 'amount', 'paid_on', 'account_name', 'created_by')
    readonly_fields = tuple(field.name for field in PayablePayment._meta.fields)
    actions = None
    def get_queryset(self, request):
        return super().get_queryset(request).filter(installment__plan__purchase__store__in=get_accessible_stores(request.user))
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
