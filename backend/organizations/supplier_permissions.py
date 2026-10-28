from django.core.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission
from .access_permissions import fresh_actor

CODES={'view':'view','create':'add','update':'change','archive':'archive','restore':'restore'}
def supplier_capabilities(user):
    view=bool(user and user.is_active and user.has_perm('organizations.view_supplier'))
    return {action:bool(view and user.has_perm(f'organizations.{code}_supplier')) for action,code in CODES.items()}

def require_supplier(user,action):
    if not isinstance(action,str) or not supplier_capabilities(user).get(action,False):
        raise PermissionDenied('Você não tem permissão para esta ação de fornecedor.')

class SupplierPermission(BasePermission):
    message='Você não tem permissão para esta ação de fornecedor.'
    def has_permission(self,request,view):
        user=fresh_actor(request)
        if user is None:return False
        request.user=user
        if getattr(view,'access_only',False):return True
        caps=supplier_capabilities(user)
        if request.method=='POST':
            action=request.data.get('action') if isinstance(request.data,dict) else None
            return isinstance(action,str) and caps.get(action,False)
        return caps['view']
