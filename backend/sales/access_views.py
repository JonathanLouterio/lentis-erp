from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from organizations.access_permissions import FreshActiveUser, fresh_actor
from organizations.models import Customer, Product
from .access_permissions import SaleActionPermission, sale_capabilities
from .models import FinancialAccount, PaymentMethod
from .payment_serializers import MethodSerializer
from .views import SalesBaseView


@method_decorator(never_cache, name='dispatch')
class SaleAccessView(SalesBaseView):
    permission_classes = [IsAuthenticated, FreshActiveUser]

    def get(self, request):
        store = self._selected_store()
        return Response({'store_id': store.pk, **sale_capabilities(fresh_actor(request))})


@method_decorator(never_cache, name='dispatch')
class SaleOptionsView(SalesBaseView):
    permission_classes = [IsAuthenticated, SaleActionPermission]
    sale_actions = {'GET': 'any'}

    def get(self, request):
        store = self._selected_store()
        user = fresh_actor(request)
        from .commercial_services import current_policy, can_approve
        role, limit, configured = current_policy(user, store)
        # Nenhum custo, saldo bancário, endereço, contato ou observação do cadastro.
        accounts = FinancialAccount.objects.filter(store=store, is_active=True)
        products = list(Product.objects.filter(store=store, is_active=True).values(
            'id', 'internal_code', 'name', 'barcode', 'sale_price', 'stock_quantity'))
        for product in products:
            for field in ('sale_price', 'stock_quantity'):
                product[field] = str(product[field])
        return Response({
            'customers': list(Customer.objects.filter(store=store, is_active=True).values('id', 'name')),
            'products': products,
            'payment_options': {
                'methods': MethodSerializer(PaymentMethod.objects.filter(store=store, is_active=True), many=True).data,
                'accounts': [{'id': a.pk, 'name': a.name, 'code': a.code, 'cash_box': a.cash_box,
                    'cash_control_enabled': a.cash_sessions.exists(),
                    'cash_is_open': a.cash_sessions.filter(closed_at__isnull=True).exists()} for a in accounts],
                'allow_negative_stock': store.allow_negative_stock,
                'discount_limit_percentage': str(limit), 'discount_policy_configured': configured,
                'can_approve_discount': can_approve(user, store), 'discount_role': role,
                'can_receive': user.is_staff or user.is_superuser,
            },
        })
