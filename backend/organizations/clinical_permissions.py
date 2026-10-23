"""Capacidades clínicas e seções do histórico, sem reutilizar caches de permissão."""
from django.contrib.auth import get_user_model
from rest_framework.permissions import BasePermission
from .access_permissions import fresh_actor

def current_clinical_user(user):
    if not user or not user.is_authenticated:return None
    return get_user_model().objects.filter(pk=user.pk,is_active=True).first()

def prescription_capabilities(user):
    view=bool(user and user.is_active and user.has_perm('organizations.view_prescription'))
    return {'view':view,'create':bool(view and user.has_perm('organizations.add_prescription')),
        'update':bool(view and user.has_perm('organizations.change_prescription')),
        'archive':bool(view and user.has_perm('organizations.archive_prescription'))}

def clinical_access(user):
    history=bool(user and user.is_active and user.has_perm('organizations.view_customer') and user.has_perm('organizations.view_customer_history'))
    codes={'sales':'sales.view_sale','quotes':'sales.view_quote','orders':'sales.view_serviceorder','installments':'sales.view_receivable','prescriptions':'organizations.view_prescription'}
    return {'prescriptions':prescription_capabilities(user),'history':history,
        'sections':{key:bool(history and user.has_perm(code)) for key,code in codes.items()}}

class ClinicalActionPermission(BasePermission):
    message='Você não tem permissão para esta ação clínica ou de histórico.'
    def has_permission(self,request,view):
        user=fresh_actor(request)
        if user is None:return False
        request.user=user
        if getattr(view,'access_only',False):return True
        if getattr(view,'customer_history',False):return clinical_access(user)['history']
        caps=prescription_capabilities(user)
        if request.method.lower() not in view.http_method_names:return caps['view']
        action=getattr(view,'clinical_action',None)
        if action:return caps[action]
        return caps['create' if request.method=='POST' else 'update' if request.method=='PUT' else 'view']
