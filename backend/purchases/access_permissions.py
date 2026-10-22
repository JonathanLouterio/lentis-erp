"""Direitos comerciais e financeiros de compras, lidos da conta atual."""
from django.core.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission
from organizations.access_permissions import fresh_actor

PURCHASE_CODES={'view':'view_purchase','create':'add_purchase','update':'change_purchase','receive':'receive_purchase','cancel':'cancel_purchase','update_cost':'update_purchase_cost'}

def purchase_capabilities(user):
    view=bool(user and user.is_active and user.has_perm('purchases.view_purchase'))
    result={action:bool(view and user.has_perm('purchases.'+code)) for action,code in PURCHASE_CODES.items()}
    result['update_cost'] &= result['receive']
    return result

def payable_capabilities(user):
    view=bool(user and user.is_active and user.has_perm('purchases.view_payableplan'))
    return {'view':view,'generate':bool(view and user.has_perm('purchases.add_payableplan') and user.has_perm('purchases.view_purchase')),
        'pay':bool(view and user.has_perm('purchases.pay_payable')),'reverse':bool(view and user.has_perm('purchases.reverse_payable'))}

def require_purchase(user,action,update_cost=False):
    caps=purchase_capabilities(user)
    if not isinstance(action,str) or not caps.get(action,False) or (action=='receive' and update_cost and not caps['update_cost']):
        raise PermissionDenied('Você não tem permissão para esta ação de compra.')

def available_purchase_actions(purchase,user):
    caps=purchase_capabilities(user)
    for action in ('update','receive','cancel','update_cost'):caps[action] &= purchase.status=='draft'
    return caps

class PurchaseActionPermission(BasePermission):
    message='Você não tem permissão para esta ação de compra.'
    def has_permission(self,request,view):
        user=fresh_actor(request)
        if user is None:return False
        request.user=user
        caps=purchase_capabilities(user)
        if getattr(view,'access_only',False):return True
        if getattr(view,'catalog_options',False):return caps['create'] or caps['update']
        if request.method.lower() not in view.http_method_names:return caps['view']
        if request.method=='POST':
            action=request.data.get('action') if isinstance(request.data,dict) else None
            return isinstance(action,str) and caps.get(action,False)
        return caps['view']

class PayableActionPermission(BasePermission):
    message='Você não tem permissão para esta ação de contas a pagar.'
    def has_permission(self,request,view):
        user=fresh_actor(request)
        if user is None:return False
        request.user=user
        caps=payable_capabilities(user)
        if request.method.lower() not in view.http_method_names:return caps['view']
        return caps[getattr(view,'payable_action','generate')] if request.method=='POST' else caps['view']
