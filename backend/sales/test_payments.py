from datetime import date
from decimal import Decimal
from io import StringIO
from unittest.mock import patch
from uuid import uuid4

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, RequestFactory
from rest_framework.test import APIClient

from accounts.models import StoreMembership
from organizations.models import Company, Customer, Product, StockMovement, Store
from .models import CheckoutRequest, FinancialAccount, FinancialEntry, PaymentMethod, Receivable, Sale, SaleItem
from .payment_services import schedule


class PaymentCheckoutTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='seller_pay', password='test-only-password')
        self.admin = get_user_model().objects.create_user(username='admin_pay', is_staff=True, password='test-only-password')
        company = Company.objects.create(name='Empresa pagamentos')
        self.store = Store.objects.create(company=company, code='PAY1', name='Matriz', allow_negative_stock=False)
        self.other = Store.objects.create(company=company, code='PAY2', name='Filial')
        for user in [self.user, self.admin]:
            StoreMembership.objects.create(user=user, store=self.store, role=StoreMembership.Role.SELLER)
        self.customer = Customer.objects.create(store=self.store, name='Cliente de parcelas')
        self.product = Product.objects.create(store=self.store, internal_code='PG001', name='Óculos', sale_price=Decimal('700'), stock_quantity=Decimal('10'))
        self.account = FinancialAccount.objects.create(store=self.store, code='bank', name='Banco')
        self.other_account = FinancialAccount.objects.create(store=self.other, code='bank', name='Outro banco')
        self.methods = {kind: PaymentMethod.objects.create(store=self.store, code=kind, name=name, kind=kind) for kind, name in PaymentMethod.Kind.choices}
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = f'/api/me/sales/checkout/?store_id={self.store.pk}'

    def data(self, *, action='complete', kind='pix', amount='700', count=1, confirmed=True):
        return {
            'request_id': str(uuid4()), 'action': action, 'customer_id': self.customer.pk, 'notes': 'Teste', 'discount_amount': '0',
            'items': [{'product_id': self.product.pk, 'quantity': '1', 'unit_price': '700', 'discount_amount': '0'}],
            'payments': [{'method_id': self.methods[kind].pk, 'account_id': self.account.pk, 'amount': amount,
                'installment_count': count, 'first_due_date': '2027-01-31', 'confirmed': confirmed}],
        }

    def send(self, data=None, *, expected=200):
        response = self.client.post(self.url, data or self.data(), format='json')
        self.assertEqual(response.status_code, expected, response.data)
        return response

    def split_sale(self):
        data = self.data(amount='150')
        data['payments'].append(self.data(kind='store_credit', amount='550', count=3, confirmed=False)['payments'][0])
        return self.send(data)

    def receive(self, receivable, amount='50', *, request_id=None, expected=200, user=None, **overrides):
        self.client.force_authenticate(user or self.admin)
        data = {'request_id': request_id or str(uuid4()), 'amount': amount, 'method_id': self.methods['pix'].pk, 'account_id': self.account.pk}
        data.update(overrides)
        response = self.client.post(f'/api/me/receivables/{receivable.pk}/receive/?store_id={self.store.pk}', data, format='json')
        self.assertEqual(response.status_code, expected, response.data)
        return response

    def test_entry_and_monthly_installments_have_exact_cents(self):
        response = self.split_sale()
        self.assertEqual(response.data['total'], '700.00')
        installments = list(Receivable.objects.filter(payment__kind='store_credit').order_by('number'))
        self.assertEqual([item.amount for item in installments], [Decimal('183.34'), Decimal('183.33'), Decimal('183.33')])
        self.assertEqual([item.due_date for item in installments], [date(2027,1,31), date(2027,2,28), date(2027,3,31)])
        self.assertEqual(sum((item.amount for item in installments)), Decimal('550'))
        self.assertEqual(FinancialEntry.objects.count(), 1)
        self.assertEqual(self.account.balance, Decimal('150'))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal('9'))

    def test_same_checkout_is_replayed_without_duplicate_sale_stock_or_receipt(self):
        data = self.data()
        first, second = self.send(data), self.send(data)
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual((Sale.objects.count(), StockMovement.objects.count(), Receivable.objects.count(), FinancialEntry.objects.count()), (1,1,1,1))
        self.assertEqual(CheckoutRequest.objects.count(), 1)

    def test_changed_payload_cannot_reuse_request_identifier(self):
        data = self.data()
        self.send(data)
        data['notes'] = 'Alterado'
        self.send(data, expected=400)
        self.assertEqual(Sale.objects.count(), 1)

    def test_request_cannot_be_reused_by_another_user(self):
        data = self.data()
        self.send(data)
        self.client.force_authenticate(self.admin)
        self.send(data, expected=403)

    def test_replay_survives_archived_catalog_but_not_revoked_access(self):
        data = self.data()
        self.send(data)
        self.product.is_active = False; self.product.save()
        self.send(data)
        StoreMembership.objects.filter(user=self.user).update(is_active=False)
        self.send(data, expected=400)

    def test_saved_draft_does_not_change_stock_or_create_receivables(self):
        data = self.data(action='draft', amount='150')
        response = self.send(data)
        self.assertEqual(response.data['status'], 'draft')
        self.assertFalse(Receivable.objects.exists())
        self.assertFalse(FinancialEntry.objects.exists())
        self.assertFalse(StockMovement.objects.exists())
        data.update(request_id=str(uuid4()), sale_id=response.data['id'], action='complete')
        data['payments'][0]['amount'] = '700'
        completed = self.send(data)
        self.assertEqual(completed.data['id'], response.data['id'])
        self.assertEqual(completed.data['status'], 'completed')
        self.assertEqual(Sale.objects.count(), 1)

    def test_global_and_line_discounts_are_combined_and_paid_exactly(self):
        data = self.data(amount='620')
        data['discount_amount'] = '50'
        data['items'][0]['discount_amount'] = '30'
        response = self.send(data)
        self.assertEqual((response.data['subtotal'], response.data['discount_total'], response.data['total']), ('700.00','80.00','620.00'))
        self.assertEqual(self.account.balance, Decimal('620'))

    def test_discount_over_subtotal_rolls_back_all_changes(self):
        data = self.data(); data['discount_amount'] = '701'
        self.send(data, expected=400)
        self.assertFalse(Sale.objects.exists())
        self.assertFalse(StockMovement.objects.exists())

    def test_unallocated_or_overallocated_total_is_rejected(self):
        for amount in ['699.99', '700.01']:
            self.send(self.data(amount=amount), expected=400)
        self.assertFalse(Sale.objects.exists())

    def test_zero_total_needs_no_payment_but_requires_an_item(self):
        data = self.data(); data['discount_amount'] = '700'; data['payments'] = []
        self.send(data)
        self.assertFalse(Receivable.objects.exists())
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_credit_and_boleto_require_named_customer(self):
        for kind in ['store_credit', 'boleto']:
            data = self.data(kind=kind, confirmed=False); data['customer_id'] = None
            self.send(data, expected=400)
        self.assertFalse(Sale.objects.exists())

    def test_card_installments_are_operator_receivables_not_received_cash(self):
        response = self.send(self.data(kind='credit', count=3, confirmed=False))
        self.assertEqual(response.data['payments'][0]['kind'], 'credit')
        self.assertTrue(all(item.debtor == 'operator' for item in Receivable.objects.all()))
        self.assertFalse(FinancialEntry.objects.exists())
        self.assertEqual(self.account.balance, Decimal('0'))

    def test_card_cannot_be_falsely_confirmed(self):
        self.send(self.data(kind='credit', confirmed=True), expected=400)
        self.assertFalse(Sale.objects.exists())

    def test_cash_cannot_be_split_and_each_parcel_requires_one_cent(self):
        self.send(self.data(count=2), expected=400)
        data = self.data(kind='store_credit', amount='0.01', count=3, confirmed=False)
        data['discount_amount'] = '699.99'
        self.send(data, expected=400)

    def test_account_or_product_from_other_unit_is_rejected(self):
        data = self.data(); data['payments'][0]['account_id'] = self.other_account.pk
        self.send(data, expected=400)
        foreign = Product.objects.create(store=self.other, internal_code='OTHER', name='Outro')
        data = self.data(); data['items'][0]['product_id'] = foreign.pk
        self.send(data, expected=400)
        self.assertFalse(Sale.objects.exists())

    def test_inactive_account_or_method_is_rejected(self):
        self.account.is_active = False; self.account.save()
        self.send(expected=400)
        self.account.is_active = True; self.account.save()
        self.methods['pix'].is_active = False; self.methods['pix'].save()
        self.send(expected=400)

    def test_duplicate_product_is_rejected(self):
        data = self.data(); data['items'].append(data['items'][0].copy())
        self.send(data, expected=400)

    def test_stock_failure_preserves_existing_draft_and_payment_plan(self):
        response = self.send(self.data(action='draft'))
        data = self.data(); data['sale_id'] = response.data['id']; data['items'][0]['quantity'] = '11'; data['payments'][0]['amount'] = '7700'
        self.send(data, expected=400)
        sale = Sale.objects.get(pk=response.data['id'])
        self.assertEqual(sale.items.get().quantity, Decimal('1'))
        self.assertEqual(sale.payments.get().amount, Decimal('700'))
        self.assertFalse(Receivable.objects.exists())

    def test_financial_failure_rolls_back_stock_status_and_sale(self):
        with patch('sales.payment_services.FinancialEntry.objects.create', side_effect=ValidationError('Falha simulada')):
            self.send(expected=400)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal('10'))
        self.assertFalse(Sale.objects.exists())
        self.assertFalse(StockMovement.objects.exists())
        self.assertFalse(CheckoutRequest.objects.exists())

    def test_completed_sale_cannot_be_replaced(self):
        response = self.send()
        data = self.data(); data['sale_id'] = response.data['id']
        self.send(data, expected=400)
        self.assertEqual(FinancialEntry.objects.count(), 1)

    def test_partial_receipts_are_idempotent_and_balance_exact(self):
        self.split_sale()
        receivable = Receivable.objects.filter(payment__kind='store_credit').first()
        request_id = str(uuid4())
        response = self.receive(receivable, request_id=request_id)
        self.assertEqual((response.data['paid_amount'], response.data['remaining_amount'], response.data['status']), ('50.00','133.34','partial'))
        self.receive(receivable, request_id=request_id)
        self.assertEqual(FinancialEntry.objects.count(), 2)
        self.receive(receivable, amount='133.34')
        self.assertEqual(Receivable.objects.get(pk=receivable.pk).status, 'paid')
        self.assertEqual(self.account.balance, Decimal('333.34'))

    def test_receipt_cannot_exceed_balance_or_reuse_key_with_new_amount(self):
        self.split_sale(); receivable = Receivable.objects.filter(payment__kind='store_credit').first()
        self.receive(receivable, amount='183.35', expected=400)
        key = str(uuid4()); self.receive(receivable, request_id=key)
        self.receive(receivable, amount='60', request_id=key, expected=400)
        self.assertEqual(FinancialEntry.objects.count(), 2)

    def test_seller_cannot_confirm_later_receipt(self):
        self.send(self.data(kind='store_credit', confirmed=False))
        self.receive(Receivable.objects.first(), user=self.user, expected=403)
        self.assertFalse(FinancialEntry.objects.exists())

    def test_receipt_cannot_target_other_unit_or_use_credit_as_cash(self):
        self.send(self.data(kind='store_credit', confirmed=False)); receivable = Receivable.objects.first()
        self.receive(receivable, account_id=self.other_account.pk, expected=400)
        self.receive(receivable, method_id=self.methods['credit'].pk, expected=400)
        self.assertFalse(FinancialEntry.objects.exists())

    def test_cancellation_reverses_entry_and_partial_receipts_once_and_closes_parcels(self):
        response = self.split_sale(); receivable = Receivable.objects.filter(payment__kind='store_credit').first()
        self.receive(receivable)
        url = f'/api/me/sales/{response.data["id"]}/cancel/?store_id={self.store.pk}'
        for _ in range(2):
            result = self.client.post(url, {'reason': 'Devolução'}, format='json')
            self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(self.account.balance, Decimal('0'))
        self.assertEqual(FinancialEntry.objects.count(), 4)
        self.assertTrue(all(item.status == 'cancelled' and item.remaining_amount == 0 for item in Receivable.objects.all()))
        self.product.refresh_from_db(); self.assertEqual(self.product.stock_quantity, Decimal('10'))
        self.receive(receivable, expected=400)

    def test_receivables_are_scoped_and_filter_customer_or_operator(self):
        self.split_sale(); self.send(self.data(kind='credit', confirmed=False))
        url = f'/api/me/receivables/?store_id={self.store.pk}'
        response = self.client.get(url); self.assertEqual(response.data['count'], 4)
        response = self.client.get(url+'&debtor=operator'); self.assertEqual(response.data['count'], 1)
        response = self.client.get(url+'&status=paid'); self.assertEqual(response.data['count'], 1)
        self.assertEqual(self.client.get(f'/api/me/receivables/?store_id={self.other.pk}').status_code, 400)
        self.assertEqual(self.client.get(url+'&status=unknown').status_code, 400)

    def test_legacy_finalize_endpoint_cannot_bypass_payment_plan(self):
        sale = Sale.objects.create(store=self.store, created_by=self.user)
        SaleItem.objects.create(sale=sale, product=self.product, quantity=1)
        response = self.client.post(f'/api/me/sales/{sale.pk}/finalize/?store_id={self.store.pk}', {}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(StockMovement.objects.exists())

    def test_anonymous_and_session_posts_without_csrf_are_denied(self):
        self.client.force_authenticate(None)
        self.send(expected=403)
        csrf_client = APIClient(enforce_csrf_checks=True); csrf_client.force_login(self.admin)
        self.assertEqual(csrf_client.post(self.url, self.data(), format='json').status_code, 403)
        self.client.force_authenticate(self.user); self.send(self.data(kind='store_credit', confirmed=False))
        receivable = Receivable.objects.first()
        self.assertEqual(csrf_client.post(f'/api/me/receivables/{receivable.pk}/receive/?store_id={self.store.pk}', {}, format='json').status_code, 403)

    def test_financial_history_is_immutable_and_admin_cannot_edit(self):
        self.send()
        for obj in [Receivable.objects.first(), FinancialEntry.objects.first()]:
            with self.assertRaises(ValidationError): obj.save()
            with self.assertRaises(ValidationError): obj.delete()
            model_admin = admin.site._registry[type(obj)]
            request = RequestFactory().get('/admin/'); request.user = self.admin
            self.assertFalse(model_admin.has_add_permission(request))
            self.assertFalse(model_admin.has_change_permission(request, obj))
            self.assertFalse(model_admin.has_delete_permission(request, obj))

    def test_setup_command_is_idempotent_and_preserves_custom_names(self):
        output = StringIO()
        call_command('setup_payments', store_id=self.store.pk, stdout=output)
        count = PaymentMethod.objects.count(), FinancialAccount.objects.count()
        self.account.name = 'Banco personalizado'; self.account.save()
        call_command('setup_payments', store_id=self.store.pk, stdout=output)
        self.assertEqual(count, (PaymentMethod.objects.count(), FinancialAccount.objects.count()))
        self.account.refresh_from_db(); self.assertEqual(self.account.name, 'Banco personalizado')

    def test_month_end_and_leap_year_schedule(self):
        self.assertEqual([due for due, _ in schedule(Decimal('1'),3,date(2028,1,31))], [date(2028,1,31), date(2028,2,29), date(2028,3,31)])
        with self.assertRaises(ValidationError): schedule(Decimal('1'),2,date(9999,12,31))


from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import close_old_connections
from django.test import TransactionTestCase, skipUnlessDBFeature


@skipUnlessDBFeature('has_select_for_update')
class PaymentConcurrencyTests(TransactionTestCase):
    setUp = PaymentCheckoutTests.setUp
    data = PaymentCheckoutTests.data

    def parallel_posts(self, url, data, user):
        barrier = Barrier(2)
        def request_once():
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(get_user_model().objects.get(pk=user.pk))
                barrier.wait(timeout=10)
                response = client.post(url, data, format='json')
                return response.status_code, response.data
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(request_once) for _ in range(2)]
            results = [future.result(timeout=30) for future in futures]
        for code, body in results:
            self.assertEqual(code, 200, body)
        return results

    def test_concurrent_checkout_retry_creates_one_sale_and_receipt(self):
        results = self.parallel_posts(self.url, self.data(), self.user)
        self.assertEqual(results[0][1]['id'], results[1][1]['id'])
        self.assertEqual((Sale.objects.count(), StockMovement.objects.count(), FinancialEntry.objects.count()), (1,1,1))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal('9'))

    def test_concurrent_receipt_retry_posts_once(self):
        self.client.post(self.url, self.data(kind='store_credit', confirmed=False), format='json')
        receivable = Receivable.objects.first()
        payload = {'request_id': str(uuid4()), 'amount': '50', 'account_id': self.account.pk, 'method_id': self.methods['pix'].pk}
        self.parallel_posts(f'/api/me/receivables/{receivable.pk}/receive/?store_id={self.store.pk}', payload, self.admin)
        self.assertEqual(FinancialEntry.objects.count(), 1)
        self.assertEqual(receivable.paid_amount, Decimal('50'))
