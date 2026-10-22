from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from organizations.access_permissions import FreshActiveUser, fresh_actor
from organizations.models import Customer, Product
from .quote_permissions import QuoteActionPermission, quote_capabilities
from .views import SalesBaseView


@method_decorator(never_cache,name='dispatch')
class QuoteAccessView(SalesBaseView):
    permission_classes=[IsAuthenticated,FreshActiveUser]

    def get(self,request):
        store=self._selected_store();user=fresh_actor(request)
        return Response({'store_id':store.pk,'actions':quote_capabilities(user),'can_open_sale':user.has_perm('sales.view_sale')})


@method_decorator(never_cache,name='dispatch')
class QuoteOptionsView(SalesBaseView):
    permission_classes=[IsAuthenticated,QuoteActionPermission]
    quote_actions={'GET':'options'}

    def get(self,request):
        store=self._selected_store()
        products=list(Product.objects.filter(store=store,is_active=True).values('id','internal_code','name','sale_price'))
        for product in products:product['sale_price']=str(product['sale_price'])
        return Response({'customers':list(Customer.objects.filter(store=store,is_active=True).values('id','name')),'products':products})
