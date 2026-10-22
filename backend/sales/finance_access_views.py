from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from organizations.access_permissions import FreshActiveUser, fresh_actor
from .finance_permissions import finance_capabilities
from .views import SalesBaseView


@method_decorator(never_cache,name='dispatch')
class FinanceAccessView(SalesBaseView):
    permission_classes=[IsAuthenticated,FreshActiveUser]

    def get(self,request):
        store=self._selected_store()
        return Response({'store_id':store.pk,**finance_capabilities(fresh_actor(request))})
