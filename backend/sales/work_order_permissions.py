"""Direitos de OS independentes das permissões comerciais e clínicas."""
from django.core.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission
from organizations.access_permissions import fresh_actor

CODES={'view':'view','create':'add','update':'change','advance':'advance','rework':'rework','cancel':'cancel'}

def order_capabilities(user):
    active=bool(user and user.is_active)
    view=active and user.has_perm('sales.view_serviceorder')
    return {action:bool(view and user.has_perm(f'sales.{code}_serviceorder')) for action,code in CODES.items()}

def require_order_action(user,action):
    if not order_capabilities(user).get(action,False):
        raise PermissionDenied('Você não tem permissão para esta ação de ordem de serviço.')

def available_order_actions(order,user):
    caps=order_capabilities(user)
    active=order.status not in ('delivered','cancelled')
    completed=order.sale.status=='completed'
    caps['update'] &= active and completed
    caps['advance'] &= active and completed
    caps['rework'] &= completed and order.status in ('checking','ready')
    caps['cancel'] &= active
    return caps

class OrderActionPermission(BasePermission):
    message='Você não tem permissão para esta ação de ordem de serviço.'
    def has_permission(self,request,view):
        actor=fresh_actor(request)
        if actor is None:return False
        request.user=actor
        caps=order_capabilities(actor)
        if request.method=='POST':
            action=request.data.get('action') if isinstance(request.data,dict) else None
            return isinstance(action,str) and caps.get(action,False)
        if getattr(view,'creation_options',False):return caps['create']
        return caps['view']
