from django.contrib.auth.models import Permission,Group
from django.test import TestCase
from accounts.models import StoreMembership
from . import test_payments as fixtures
from .models import Sale

class InsightPermissionTests(TestCase):
    setUp=fixtures.PaymentCheckoutTests.setUp

    def grant(self,*codes):
        self.user.user_permissions.clear()
        self.user.user_permissions.add(*Permission.objects.filter(codename__in=codes))

    def dashboard(self,**extra):return self.client.get('/api/me/dashboard/',{'store_id':self.store.pk,**extra})
    def report(self,kind='sales',**extra):return self.client.get('/api/me/reports/',{'store_id':self.store.pk,'report':kind,**extra})
    def options(self):return self.client.get('/api/me/reports/options/',{'store_id':self.store.pk})

    def test_source_read_alone_does_not_grant_dashboard_or_reports(self):
        self.grant('view_sale','view_receivable')
        self.assertEqual(self.dashboard().status_code,403)
        self.assertEqual(self.report().status_code,403);self.assertEqual(self.options().status_code,403)

    def test_dashboard_permission_alone_masks_every_block_and_series(self):
        self.grant('view_dashboard');response=self.dashboard()
        self.assertEqual(response.status_code,200,response.data)
        for key in ('sales','receipts','receivables','stock','cash'):self.assertIsNone(response.data[key])
        self.assertEqual(response.data['recent_sales'],[])
        self.assertTrue(all(row['sales'] is None and row['received'] is None and row['sales_count'] is None for row in response.data['chart']))

    def test_sales_dashboard_does_not_leak_finance_cash_or_stock(self):
        self.grant('view_dashboard','view_sale');response=self.dashboard()
        self.assertEqual(response.status_code,200);self.assertIsNotNone(response.data['sales'])
        self.assertEqual(response.data['chart'][0]['sales'],'0.00');self.assertIsNone(response.data['chart'][0]['received'])
        for key in ('receipts','receivables','cash','stock'):self.assertIsNone(response.data[key])

    def test_receivables_do_not_grant_cash_or_collected_receipt_totals(self):
        self.grant('view_dashboard','view_receivable');response=self.dashboard()
        self.assertIsNotNone(response.data['receivables']);self.assertIsNone(response.data['receipts']);self.assertIsNone(response.data['cash']);self.assertIsNone(response.data['sales'])

    def test_receipt_totals_require_both_financial_source_rights(self):
        self.grant('view_dashboard','view_receivable','view_financialentry')
        self.assertIsNotNone(self.dashboard().data['receipts'])
        self.grant('view_dashboard','view_financialentry');self.assertIsNone(self.dashboard().data['receipts'])

    def test_stock_and_cash_read_are_independent(self):
        self.grant('view_dashboard','view_stockmovement');response=self.dashboard()
        self.assertIsNotNone(response.data['stock']);self.assertIsNone(response.data['cash'])
        self.grant('view_dashboard','view_cashsession');response=self.dashboard()
        self.assertIsNotNone(response.data['cash']);self.assertIsNone(response.data['stock'])

    def test_report_consultation_does_not_grant_export(self):
        self.grant('view_reports','view_sale')
        self.assertEqual(self.report().status_code,200)
        self.assertEqual(self.report(export='csv').status_code,403)
        self.assertFalse(self.options().data['can_export'])
        self.assertEqual([r['key'] for r in self.options().data['reports']],['sales'])

    def test_export_without_consultation_or_source_is_denied(self):
        self.grant('export_reports','view_sale');self.assertEqual(self.report(export='csv').status_code,403)
        self.grant('view_reports','export_reports');self.assertEqual(self.report(export='csv').status_code,403)
        self.grant('view_reports','export_reports','view_sale');self.assertEqual(self.report(export='csv').status_code,200)

    def test_each_report_needs_its_own_source_permission(self):
        self.grant('view_reports','view_receivable');self.assertEqual(self.report('receivables').status_code,200)
        for kind in ('sales','movements','payables'):self.assertEqual(self.report(kind).status_code,403)
        self.assertEqual(self.options().data['accounts'],[])
        self.grant('view_reports','view_financialentry');self.assertEqual(self.report('movements').status_code,403)
        self.user.user_permissions.add(Permission.objects.get(content_type__app_label='purchases',codename='view_payableplan'))
        self.assertEqual(self.report('movements').status_code,200)

    def test_group_export_revocation_preserves_consultation(self):
        self.grant('view_reports','view_sale')
        group=Group.objects.create(name='Exportadores');group.permissions.add(Permission.objects.get(content_type__app_label='sales',codename='export_reports'));self.user.groups.add(group)
        self.assertEqual(self.report(export='csv').status_code,200)
        self.user.has_perm('sales.export_reports');group.permissions.clear()
        self.assertEqual(self.report(export='csv').status_code,403);self.assertEqual(self.report().status_code,200)

    def test_revoking_source_hides_dashboard_and_report_in_same_session(self):
        self.grant('view_dashboard','view_reports','export_reports','view_sale')
        self.assertIsNotNone(self.dashboard().data['sales'])
        self.user.has_perm('sales.view_sale');self.user.user_permissions.remove(Permission.objects.get(content_type__app_label='sales',codename='view_sale'))
        self.assertIsNone(self.dashboard().data['sales']);self.assertEqual(self.report().status_code,403)
        self.assertEqual(self.options().data['reports'],[])

    def test_scoped_unit_and_disabled_membership_block_all_reads(self):
        self.grant('view_dashboard','view_reports','export_reports','view_sale')
        self.assertEqual(self.dashboard(store_id=self.other.pk).status_code,400)
        self.assertEqual(self.report(store_id=self.other.pk).status_code,400)
        StoreMembership.objects.filter(user=self.user).update(is_active=False)
        self.assertEqual(self.dashboard().status_code,400);self.assertEqual(self.report(export='csv').status_code,400)

    def test_own_metadata_no_data_and_inactive_or_anonymous_denied(self):
        self.grant('view_dashboard');url=f'/api/me/insight-access/?store_id={self.store.pk}'
        response=self.client.get(url);self.assertEqual(response.status_code,200)
        self.assertTrue(response.data['dashboard']);self.assertFalse(any(response.data['reports'].values()));self.assertNotIn('customers',response.data)
        self.assertIn('no-store',response['Cache-Control'])
        type(self.user).objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.client.get(url).status_code,403)
        self.client.force_authenticate(None);self.assertEqual(self.client.get(url).status_code,403)

    def test_insight_reads_do_not_mutate_sales(self):
        self.grant('view_dashboard','view_reports','export_reports','view_sale')
        before=Sale.objects.count();self.dashboard();self.report();self.report(export='csv')
        self.assertEqual(Sale.objects.count(),before)
