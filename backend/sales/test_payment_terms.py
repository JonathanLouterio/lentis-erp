from datetime import date
from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from . import test_payments as fixtures
from .models import CheckoutRequest, FinancialEntry, PaymentMethod, Receivable, Sale, SaleItem, SalePayment
from .payment_schedule import schedule
from .payment_services import complete_sale
from organizations.models import StockMovement


class PaymentTermsTests(TestCase):
    setUp = fixtures.PaymentCheckoutTests.setUp
    data = fixtures.PaymentCheckoutTests.data

    def preview(self, payments, total='700'):
        return self.client.post(f'/api/me/sales/payment-preview/?store_id={self.store.pk}', {'total': total, 'payments': payments}, format='json')

    def mixed(self):
        body = self.data(kind='store_credit', amount='550', count=3, confirmed=False)
        body['payments'][0].update(first_due_date='2028-01-31', interval_unit='months', interval_count=1)
        entry = self.data(amount='150')['payments'][0]
        body['payments'].insert(0, entry)
        return body

    def test_entry_and_monthly_balance_match_preview_and_ledger(self):
        body = self.mixed()
        preview = self.preview(body['payments'])
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(Receivable.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)
        response = self.client.post(self.url, body, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        for planned, recorded in zip(preview.data['payments'], response.data['payments']):
            self.assertEqual([(item['due_date'], item['amount']) for item in planned['installments']], [(item['due_date'], item['amount']) for item in recorded['installments']])
        self.assertEqual([item['amount'] for item in preview.data['payments'][1]['installments']], ['183.34', '183.33', '183.33'])
        self.assertEqual([item['due_date'] for item in preview.data['payments'][1]['installments']], ['2028-01-31', '2028-02-29', '2028-03-31'])
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal('150'))
        self.assertEqual(FinancialEntry.objects.count(), 1)
        self.assertEqual(sum((item.remaining_amount for item in Receivable.objects.all()), Decimal('0')), Decimal('550'))

    def test_day_interval_persists_in_draft_and_completion(self):
        body = self.data(action='draft', kind='store_credit', count=3, confirmed=False)
        body['payments'][0].update(first_due_date='2028-02-20', interval_unit='days', interval_count=15)
        response = self.client.post(self.url, body, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data['payments'][0]['interval_unit'], response.data['payments'][0]['interval_count']), ('days', 15))
        self.assertEqual(Receivable.objects.count(), 0)
        complete_sale(user=self.user, sale_id=response.data['id'])
        self.assertEqual(list(Receivable.objects.order_by('number').values_list('due_date', flat=True)), [date(2028, 2, 20), date(2028, 3, 6), date(2028, 3, 21)])

    def test_two_month_interval_keeps_original_day(self):
        self.assertEqual([due for due, _ in schedule(Decimal('10'), 3, date(2027, 12, 31), 'months', 2)], [date(2027, 12, 31), date(2028, 2, 29), date(2028, 4, 30)])

    def test_omitted_interval_preserves_monthly_behavior(self):
        body = self.data(kind='credit', count=2, confirmed=False)
        response = self.client.post(self.url, body, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['payments'][0]['interval_unit'], 'months')
        self.assertEqual(response.data['payments'][0]['interval_count'], 1)

    def test_method_limit_blocks_preview_and_completion_without_effects(self):
        method = self.methods['store_credit']; method.max_installments = 2; method.save()
        body = self.data(kind='store_credit', count=3, confirmed=False)
        self.assertEqual(self.preview(body['payments']).status_code, 400)
        self.assertEqual(self.client.post(self.url, body, format='json').status_code, 400)
        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)
        self.assertEqual(FinancialEntry.objects.count(), 0)

    def test_limit_rechecked_for_saved_draft_and_completed_history_stays(self):
        body = self.data(action='draft', kind='store_credit', count=3, confirmed=False)
        response = self.client.post(self.url, body, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        method = self.methods['store_credit']; method.max_installments = 2; method.save()
        with self.assertRaises(ValidationError): complete_sale(user=self.user, sale_id=response.data['id'])
        self.assertEqual(Receivable.objects.count(), 0)
        method.max_installments = 3; method.save()
        sale = complete_sale(user=self.user, sale_id=response.data['id'])
        recorded = list(Receivable.objects.values_list('due_date', 'amount'))
        method.max_installments = 1; method.save()
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.COMPLETED)
        self.assertEqual(list(Receivable.objects.values_list('due_date', 'amount')), recorded)

    def test_immediate_methods_never_install_in_multiple_parcels(self):
        for kind in ['cash', 'pix', 'transfer', 'debit']:
            body = self.data(kind=kind, count=2, confirmed=False)
            with self.subTest(kind=kind): self.assertEqual(self.preview(body['payments']).status_code, 400)

    def test_invalid_intervals_and_dates_rejected_before_writes(self):
        for unit, interval, due in [('weeks', 1, '2028-01-01'), ('months', 0, '2028-01-01'), ('months', 13, '2028-01-01'), ('days', 366, '2028-01-01'), ('days', 0, '2028-01-01'), ('days', 15, '2028-02-30'), ('months', 1, '9999-12-31'), ('days', 15, '9999-12-31')]:
            body = self.data(kind='store_credit', count=2, confirmed=False)
            body['payments'][0].update(interval_unit=unit, interval_count=interval, first_due_date=due)
            with self.subTest(unit=unit, interval=interval, due=due):
                self.assertEqual(self.preview(body['payments']).status_code, 400)
                self.assertEqual(self.client.post(self.url, body, format='json').status_code, 400)
        self.assertEqual(Sale.objects.count(), 0)

    def test_low_amounts_zero_total_and_allocation_mismatch(self):
        body = self.data(kind='store_credit', amount='0.02', count=3, confirmed=False)
        self.assertEqual(self.preview(body['payments'], '0.02').status_code, 400)
        self.assertEqual(self.preview(self.mixed()['payments'], '701').status_code, 400)
        response = self.preview([], '0')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['payments'], [])

    def test_maximum_installments_on_method_is_validated(self):
        for invalid in [0, 13]:
            self.methods['credit'].max_installments = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError): self.methods['credit'].save()

    def test_options_show_effective_unit_method_limit(self):
        self.methods['credit'].max_installments = 4; self.methods['credit'].save()
        response = self.client.get(f'/api/me/sales/payment-options/?store_id={self.store.pk}')
        methods = {method['kind']: method['installment_limit'] for method in response.data['methods']}
        self.assertEqual(methods['credit'], 4)
        self.assertEqual(methods['pix'], 1)

    def test_preview_does_not_modify_existing_draft(self):
        response = self.client.post(self.url, self.data(action='draft'), format='json')
        sale = Sale.objects.get(pk=response.data['id'])
        snapshot = list(SalePayment.objects.values()), list(SaleItem.objects.values()), sale.updated_at
        self.assertEqual(self.preview(self.mixed()['payments']).status_code, 200)
        sale.refresh_from_db()
        self.assertEqual(snapshot, (list(SalePayment.objects.values()), list(SaleItem.objects.values()), sale.updated_at))
        self.assertEqual(CheckoutRequest.objects.count(), 1)

    def test_preview_requires_authentication_access_and_csrf(self):
        body = self.data()['payments']
        self.client.force_authenticate(None)
        self.assertEqual(self.preview(body).status_code, 403)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.post(f'/api/me/sales/payment-preview/?store_id={self.other.pk}', {'total': '700', 'payments': body}, format='json').status_code, 400)
        browser = APIClient(enforce_csrf_checks=True); browser.force_login(self.user)
        self.assertEqual(browser.post(f'/api/me/sales/payment-preview/?store_id={self.store.pk}', {'total': '700', 'payments': body}, format='json').status_code, 403)

    def test_preview_rejects_inactive_and_other_unit_methods(self):
        body = self.data()['payments']
        self.methods['pix'].is_active = False; self.methods['pix'].save()
        self.assertEqual(self.preview(body).status_code, 400)
        body[0]['method_id'] = PaymentMethod.objects.create(store=self.other, code='x', name='Outra', kind='pix').pk
        self.assertEqual(self.preview(body).status_code, 400)

    def test_new_interval_retries_do_not_duplicate_installments(self):
        body = self.mixed(); body['payments'][1].update(interval_unit='days', interval_count=15)
        first = self.client.post(self.url, body, format='json')
        second = self.client.post(self.url, body, format='json')
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(second.data['id'], first.data['id'])
        self.assertEqual(Receivable.objects.count(), 4)
        self.assertEqual(FinancialEntry.objects.count(), 1)
        self.assertEqual(StockMovement.objects.count(), 1)
        body['payments'][1]['interval_count'] = 30
        self.assertEqual(self.client.post(self.url, body, format='json').status_code, 400)
        self.assertEqual(Receivable.objects.count(), 4)
