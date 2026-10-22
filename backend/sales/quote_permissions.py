"""Permissões atuais e transições disponíveis para propostas."""
from django.core.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import BasePermission
from organizations.access_permissions import fresh_actor

ACTIONS=('view','add','change','send','accept','reject','convert','print')


def quote_capabilities(user):
    result={action:bool(user and user.has_perm(f'sales.{action}_quote')) for action in ACTIONS}
    result['convert']=result['convert'] and user.has_perm('sales.add_sale')
    result['print']=result['print'] and result['view']
    return result


def require_quote_action(user,action,quote_id=None):
    key=('change' if quote_id is not None else 'add') if action=='save' else action
    if key not in ACTIONS: raise ValidationError('Operação de orçamento inválida.')
    if not user or not user.is_active or not quote_capabilities(user)[key]:
        raise PermissionDenied('Você não tem permissão para esta ação de orçamento.')


def available_quote_actions(quote,user):
    result=quote_capabilities(user)
    has_items=bool(list(quote.items.all()))
    result['change'] &= quote.status not in ('converted','rejected')
    result['send'] &= quote.status=='draft' and not quote.is_expired and has_items
    result['accept'] &= quote.status=='sent' and not quote.is_expired and has_items
    result['reject'] &= quote.status in ('draft','sent','accepted')
    result['convert'] &= quote.status=='accepted' and not quote.is_expired and has_items
    return result


class QuoteActionPermission(BasePermission):
    message='Você não tem permissão para esta ação de orçamento.'

    def has_permission(self,request,view):
        user=fresh_actor(request)
        if user is None:return False
        request.user=user
        capabilities=quote_capabilities(user)
        method='GET' if request.method=='HEAD' else request.method
        if method=='OPTIONS':return any(capabilities.values())
        action=getattr(view,'quote_actions',{}).get(method)
        if action is None:return True
        if action=='options':return capabilities['add'] or capabilities['change']
        if action=='transition':
            action=view.kwargs.get('action')
            if action not in ('send','accept','reject','convert'):return True
        return capabilities[action]
