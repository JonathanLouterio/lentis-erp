from rest_framework.permissions import IsAuthenticated
from .finance_permissions import FinanceActionPermission
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from .models import CashSession, FinancialAccount
from .cash_serializers import OpenCashSerializer, CashMoveSerializer, CloseCashSerializer, CashSessionSerializer, CashPostingSerializer
from .cash_services import open_cash, move_cash, close_cash
from .payment_serializers import AccountSerializer
from .views import SalesBaseView, SalesPagination, model_errors


class CashSessionsView(SalesBaseView):
    permission_classes=[IsAuthenticated,FinanceActionPermission]
    finance_actions={'GET': ['view_cashsession'], 'POST': ['add_cashsession']}

    def get(self, request):
        store = self._selected_store()
        queryset = CashSession.objects.filter(account__store=store).select_related('account', 'opened_by', 'closed_by')
        state = request.query_params.get('status', 'all')
        if state in ('open', 'closed'):
            queryset = queryset.filter(closed_at__isnull=state == 'open')
        elif state != 'all':
            raise ValidationError({'status': 'Informe all, open ou closed.'})
        pagination = SalesPagination()
        rows = pagination.paginate_queryset(queryset, request, view=self)
        return pagination.get_paginated_response(CashSessionSerializer(rows, many=True, context={'request': request}).data)

    def post(self, request):
        store = self._selected_store()
        values = self.write_serializer(OpenCashSerializer, request.data, store).validated_data
        with model_errors():
            session = open_cash(user=request.user, store=store, **values)
        return Response(CashSessionSerializer(session, context={'request': request}).data)


class CashDetailView(SalesBaseView):
    permission_classes=[IsAuthenticated,FinanceActionPermission]
    finance_actions={'GET': ['view_cashsession']}

    def selected(self, session_id):
        return get_object_or_404(CashSession.objects.select_related('account', 'opened_by', 'closed_by'), pk=session_id, account__store=self._selected_store())
    def get(self, request, session_id):
        return Response(CashSessionSerializer(self.selected(session_id), context={'request': request}).data)


class CashPostingsView(CashDetailView):
    permission_classes=[IsAuthenticated,FinanceActionPermission]
    finance_actions={'GET': ['view_cashsession'], 'POST': ['move_cash']}

    def get(self, request, session_id):
        session = self.selected(session_id)
        pagination = SalesPagination()
        rows = pagination.paginate_queryset(session.postings.select_related('created_by', 'financial_entry__receivable__payment', 'payable_payment__installment__plan'), request, view=self)
        return pagination.get_paginated_response(CashPostingSerializer(rows, many=True).data)
    def post(self, request, session_id):
        store = self._selected_store()
        values = self.write_serializer(CashMoveSerializer, request.data, store).validated_data
        with model_errors():
            posting = move_cash(user=request.user, store=store, session_id=session_id, **values)
        return Response(CashPostingSerializer(posting).data)


class CashCloseView(SalesBaseView):
    permission_classes=[IsAuthenticated,FinanceActionPermission]
    finance_actions={'POST': ['close_cash']}

    def post(self, request, session_id):
        store = self._selected_store()
        values = self.write_serializer(CloseCashSerializer, request.data, store).validated_data
        with model_errors():
            session = close_cash(user=request.user, store=store, session_id=session_id, **values)
        return Response(CashSessionSerializer(session, context={'request': request}).data)


class CashOptionsView(SalesBaseView):
    permission_classes=[IsAuthenticated,FinanceActionPermission]
    finance_actions={'GET': 'cash-any'}

    def get(self, request):
        store = self._selected_store()
        from django.db.models import Q
        accounts = FinancialAccount.objects.filter(store=store, is_active=True).filter(Q(is_cash_box=True) | Q(code='cash'))
        data=AccountSerializer(accounts, many=True).data
        if not request.user.has_perm('sales.view_financialaccount'):
            for account in data: account.pop('balance',None)
        return Response({'accounts':data},headers={'Cache-Control':'no-store, private'})
