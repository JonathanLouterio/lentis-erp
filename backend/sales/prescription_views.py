from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .access_permissions import SaleActionPermission
from .views import SalesBaseView
from .prescription_services import can_view_prescriptions, prescription_output


class PrescriptionAccessView(SalesBaseView):
    def get(self,request):
        self._selected_store()
        return Response({'can_view':can_view_prescriptions(request.user)},headers={'Cache-Control':'no-store, private'})


class SalePrescriptionHistoryView(SalesBaseView):
    permission_classes = [IsAuthenticated, SaleActionPermission]
    sale_actions = {"GET": ["view"]}

    def get(self,request,sale_id):
        sale=self.selected_sale(sale_id)
        if not can_view_prescriptions(request.user):raise PermissionDenied('Você não tem permissão de consultar receitas.')
        return Response([prescription_output(record) for record in sale.prescription_history.select_related('created_by')],headers={'Cache-Control':'no-store, private'})
