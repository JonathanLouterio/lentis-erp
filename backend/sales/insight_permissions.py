"""Consulta do painel, relatórios e exportação preservam os direitos de origem."""
from rest_framework.permissions import BasePermission
from organizations.access_permissions import fresh_actor

def dashboard_sections(user):
    active=bool(user and user.is_active)
    def has(code):return bool(active and user.has_perm(code))
    return {'sales':has('sales.view_sale'), 'receipts':has('sales.view_receivable') and has('sales.view_financialentry'),
        'receivables':has('sales.view_receivable'), 'stock':has('organizations.view_product') or has('organizations.view_stockmovement'), 'cash':has('sales.view_cashsession')}

def report_allowed(user,permissions):
    return bool(user and user.is_active and user.has_perm('sales.view_reports') and all(user.has_perm(code) for code in permissions))

def insight_access(user):
    from .report_services import REPORTS
    active=bool(user and user.is_active)
    def has(code):return bool(active and user.has_perm(code))
    return {'dashboard':has('sales.view_dashboard'),'sections':dashboard_sections(user),
        'reports':{key:report_allowed(user,spec['permissions']) for key,spec in REPORTS.items()},
        'export':has('sales.view_reports') and has('sales.export_reports'),
        'shortcuts':{'new-sale':has('sales.add_sale'),'new-customer':has('organizations.add_customer'),
            'receivables':has('sales.view_receivable'), 'stock':has('organizations.view_stockmovement') or has('organizations.add_stockmovement'),
            'cash':has('sales.view_cashsession'),'sale':has('sales.view_sale')}}

class InsightPermission(BasePermission):
    message='Você não tem permissão para esta consulta ou exportação.'
    def has_permission(self,request,view):
        actor=fresh_actor(request)
        if actor is None:return False
        request.user=actor
        if getattr(view,'access_only',False):return True
        action=getattr(view,'insight_action','reports')
        if not actor.has_perm('sales.view_dashboard' if action=='dashboard' else 'sales.view_reports'):return False
        if 'export' in request.query_params and not actor.has_perm('sales.export_reports'):return False
        return True
