from rest_framework.response import Response
from .views import SalesBaseView
from .insight_permissions import InsightPermission,insight_access

class InsightAccessView(SalesBaseView):
    permission_classes=[InsightPermission]
    access_only=True
    http_method_names=['get','head','options']
    def get(self,request):
        store=self._selected_store()
        return Response({'store_id':store.pk,**insight_access(request.user)},headers={'Cache-Control':'no-store, private'})
