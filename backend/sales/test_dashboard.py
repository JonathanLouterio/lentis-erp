from datetime import datetime, timedelta, timezone as utc
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4
from django.test import TestCase
from rest_framework.test import APIClient
from . import test_payments as fixtures
from .models import CashSession, FinancialEntry, Receivable, Sale, CashPosting, FinancialAccount, PaymentMethod
from organizations.models import Product
from accounts.models import StoreMembership

NOW = datetime(2026, 10, 13, 15, 0, tzinfo=utc.utc)


class DashboardTests(TestCase):
    setUp = fixtures.PaymentCheckoutTests.setUp
    data = fixtures.PaymentCheckoutTests.data

    def dashboard(self, **params):
        params.setdefault('store_id', self.store.pk)
        with patch('django.utils.timezone.now', return_value=NOW):
            return self.client.get('/api/me/dashboard/', params)

    def sale(self, at=NOW, **options):
        with patch('django.utils.timezone.now', return_value=at):
            response = self.client.post(self.url, self.data(**options), format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_empty_dashboard_has_zeroes_and_a_day(self):
        response = self.dashboard()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['sales']['total'], '0.00')
        self.assertEqual(response.data['receipts']['net'], '0.00')
        self.assertIsNone(response.data['sales']['variation'])
        self.assertEqual(len(response.data['chart']), 1)
        self.assertEqual(response.data['today'], '2026-10-13')

    def test_sales_receipts_and_customer_credit_are_separate(self):
        self.sale(kind='store_credit', confirmed=False, count=3)
        data = self.dashboard().data
        self.assertEqual(data['sales']['total'], '700.00')
        self.assertEqual(data['sales']['ticket'], '700.00')
        self.assertEqual(data['receipts']['net'], '0.00')
        self.assertEqual(data['receivables']['customer']['amount'], '700.00')
        self.assertEqual(data['receivables']['customer']['count'], 3)

    def test_previous_equal_period_and_chart_zero_days(self):
        self.sale(at=NOW - timedelta(days=1))
        self.sale()
        data = self.dashboard().data
        self.assertEqual(data['sales']['previous_total'], '700.00')
        self.assertEqual(data['sales']['variation'], '0.00')
        data = self.dashboard(preset='7days').data
        self.assertEqual(len(data['chart']), 7)
        self.assertEqual(sum(item['sales_count'] for item in data['chart']), 2)
        self.assertEqual(data['chart'][0]['sales'], '0.00')

    def test_local_day_boundaries_use_sao_paulo(self):
        self.sale(at=datetime(2026, 10, 13, 2, 59, tzinfo=utc.utc))
        self.sale(at=datetime(2026, 10, 13, 3, 0, tzinfo=utc.utc))
        data = self.dashboard().data
        self.assertEqual(data['sales']['count'], 1)
        self.assertEqual(data['sales']['previous_count'], 1)
        self.assertEqual(data['receipts']['gross'], '700.00')

    def test_cancelled_sale_is_excluded_and_today_refund_is_signed(self):
        sale = self.sale(at=NOW - timedelta(days=1))
        self.client.force_authenticate(self.admin)
        with patch('django.utils.timezone.now', return_value=NOW):
            response = self.client.post(f'/api/me/sales/{sale["id"]}/cancel/?store_id={self.store.pk}', {'reason': 'Devolução'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        data = self.dashboard().data
        self.assertEqual(data['sales']['count'], 0)
        self.assertEqual(data['receipts']['gross'], '0.00')
        self.assertEqual(data['receipts']['refunds'], '700.00')
        self.assertEqual(data['receipts']['net'], '-700.00')
        self.assertEqual(data['chart'][0]['received'], '-700.00')

    def test_multiple_partial_receipts_do_not_multiply_debt(self):
        self.sale(kind='store_credit', confirmed=False)
        row = Receivable.objects.get()
        self.client.force_authenticate(self.admin)
        for amount in ['50', '25']:
            with patch('django.utils.timezone.now', return_value=NOW):
                response = self.client.post(f'/api/me/receivables/{row.pk}/receive/?store_id={self.store.pk}', {'request_id': str(uuid4()), 'amount': amount, 'account_id': self.account.pk, 'method_id': self.methods['pix'].pk}, format='json')
            self.assertEqual(response.status_code, 200, response.data)
        data = self.dashboard().data
        self.assertEqual(data['receivables']['customer']['amount'], '625.00')
        self.assertEqual(data['sales']['total'], '700.00')
        self.assertEqual(data['receipts']['net'], '75.00')

    def test_card_operator_is_separate_from_customer(self):
        self.sale(kind='credit', confirmed=False, count=2)
        data = self.dashboard().data
        self.assertEqual(data['receivables']['operator']['amount'], '700.00')
        self.assertEqual(data['receivables']['customer']['amount'], '0.00')

    def test_overdue_and_today_use_current_state_even_for_old_filter(self):
        with patch('django.utils.timezone.now', return_value=NOW):
            body = self.data(kind='store_credit', count=2, confirmed=False)
            body['payments'][0]['first_due_date'] = '2026-09-13'
            response = self.client.post(self.url, body, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        data = self.dashboard(preset='custom', start='2026-01-01', end='2026-01-10').data
        self.assertEqual(data['sales']['count'], 0)
        self.assertEqual(data['receivables']['overdue']['amount'], '350.00')
        self.assertEqual(data['receivables']['due_today']['amount'], '350.00')

    def test_stock_is_current_and_only_active_products(self):
        self.product.stock_quantity = Decimal('-1'); self.product.save()
        Product.objects.create(store=self.store, internal_code='INACTIVE', name='Inativo', stock_quantity='0', minimum_stock='2', is_active=False)
        data = self.dashboard().data
        self.assertEqual(data['stock']['negative_count'], 1)
        self.assertEqual(data['stock']['low_count'], 1)
        self.assertEqual(data['stock']['items'][0]['id'], self.product.pk)

    def test_drafts_do_not_count_and_receipt_does_not_assume_legacy(self):
        self.sale(action='draft')
        data = self.dashboard().data
        self.assertEqual(data['sales']['count'], 0)
        self.assertEqual(data['receipts']['net'], '0.00')
        self.assertEqual(data['recent_sales'], [])

    def test_exact_item_rounding_and_global_discount(self):
        body = self.data(amount='0.01'); body['items'][0].update(quantity='0.001', unit_price='5', discount_amount='0')
        with patch('django.utils.timezone.now', return_value=NOW):
            result = self.client.post(self.url, body, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(self.dashboard().data['sales']['total'], result.data['total'])
        self.assertEqual(self.dashboard().data['sales']['total'], '0.01')
        body = self.data(amount='550'); body['discount_amount'] = '50'; body['items'][0]['discount_amount'] = '100'
        with patch('django.utils.timezone.now', return_value=NOW):
            result = self.client.post(self.url, body, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(self.dashboard().data['sales']['total'], '550.01')


    def test_open_cash_uses_physical_balance_and_excludes_closed_cash(self):
        account = FinancialAccount.objects.create(store=self.store, code='cash', name='Caixa')
        session = CashSession.objects.create(account=account, opened_by=self.user, opening_amount='100', opening_request=uuid4())
        CashPosting.objects.create(session=session, kind='supply', amount='20', reason='Troco', created_by=self.user, request_id=uuid4())
        data = self.dashboard().data
        self.assertEqual(data['cash']['count'], 1)
        self.assertEqual(data['cash']['expected_cash'], '120.00')
        self.assertEqual(data['receipts']['gross'], '0.00')
        from .cash_services import close_cash
        close_cash(user=self.user, store=self.store, session_id=session.pk, counted_amount=Decimal('120'), note='', request_id=uuid4())
        self.assertEqual(self.dashboard().data['cash']['count'], 0)

    def test_other_unit_records_do_not_leak_into_summary_or_lists(self):
        self.sale()
        link = StoreMembership.objects.create(user=self.user, store=self.other, role=StoreMembership.Role.SELLER)
        product = Product.objects.create(store=self.other, internal_code='SECRET', name='Produto secreto da filial', sale_price='1000', stock_quantity='10')
        method = PaymentMethod.objects.create(store=self.other, code='pix', name='Pix filial', kind='pix')
        body = self.data(amount='1000'); body['customer_id'] = None
        body['items'][0].update(product_id=product.pk, unit_price='1000')
        body['payments'][0].update(method_id=method.pk, account_id=self.other_account.pk)
        with patch('django.utils.timezone.now', return_value=NOW):
            result = self.client.post(f'/api/me/sales/checkout/?store_id={self.other.pk}', body, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        link.is_active = False; link.save()
        data = self.dashboard().data
        self.assertEqual(data['sales']['total'], '700.00')
        self.assertEqual(data['receipts']['net'], '700.00')
        self.assertNotIn(result.data['id'], [sale['id'] for sale in data['recent_sales']])

    def test_bad_periods_and_cross_unit_are_denied(self):
        for params in [dict(preset='wrong'), dict(preset='custom'), dict(preset='custom', start='2026-13-01', end='2026-10-13'), dict(preset='custom', start='2026-10-15', end='2026-10-13'), dict(preset='custom', start='2024-01-01', end='2026-10-13')]:
            with self.subTest(params=params): self.assertEqual(self.dashboard(**params).status_code, 400)
        self.assertEqual(self.dashboard(store_id=self.other.pk).status_code, 400)
        self.client.force_authenticate(None)
        self.assertEqual(self.dashboard().status_code, 403)

    def test_reads_do_not_change_records_and_details_are_bounded(self):
        self.sale()
        before = Sale.objects.count(), FinancialEntry.objects.count(), Receivable.objects.count()
        result = self.dashboard(preset='month')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertLessEqual(len(result.data['recent_sales']), 5)
        self.assertLessEqual(len(result.data['receivables']['attention']), 5)
        self.assertEqual(before, (Sale.objects.count(), FinancialEntry.objects.count(), Receivable.objects.count()))
