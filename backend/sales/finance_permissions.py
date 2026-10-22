"""Direitos de caixa e recebimentos; nenhum deles é concedido por staff ou perfil."""
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission
from organizations.access_permissions import fresh_actor

CASH = {'view':'view_cashsession', 'open':'add_cashsession', 'move':'move_cash', 'close':'close_cash'}
RECEIPTS = {'view':'view_receivable', 'receive':'receive_receivable', 'balances':'view_financialaccount'}


def finance_capabilities(user):
    return {section:{action:bool(user and user.has_perm('sales.'+code)) for action,code in actions.items()}
            for section,actions in [('cash',CASH),('receipts',RECEIPTS)]}


def require_finance(user, permission):
    actor = get_user_model().objects.filter(pk=getattr(user,'pk',None),is_active=True).first()
    if actor is None or not actor.has_perm('sales.'+permission):
        raise PermissionDenied('Você não tem permissão para esta operação de caixa ou recebimento.')
    return actor


class FinanceActionPermission(BasePermission):
    message = 'Você não tem permissão para esta operação de caixa ou recebimento.'

    def has_permission(self, request, view):
        user=fresh_actor(request)
        if user is None: return False
        request.user=user
        method='GET' if request.method=='HEAD' else request.method
        mapping=getattr(view,'finance_actions',{})
        if method=='OPTIONS': return any(any(v.values()) for v in finance_capabilities(user).values())
        codes=mapping.get(method)
        if codes is None: return True
        if codes=='cash-any': return any(finance_capabilities(user)['cash'].values())
        if codes=='payment-options':
            return user.has_perm('sales.view_receivable') or user.has_perm('sales.receive_receivable') or any(user.has_perm('sales.'+a+'_sale') for a in ['view','add','change','finalize','cancel'])
        return all(user.has_perm('sales.'+code) for code in codes)
