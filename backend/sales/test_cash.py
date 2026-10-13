from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch
from django.contrib import admin
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient
from . import test_payments as fixtures
from .models import CashSession, CashPosting, FinancialAccount, FinancialEntry, Receivable, Sale
from organizations.models import StockMovement


class CashTests(TestCase):
    setUp = fixtures.PaymentCheckoutTests.setUp
    data = fixtures.PaymentCheckoutTests.data

    def cash_account(self):
        return FinancialAccount.objects.get_or_create(store=self.store, code='cash', defaults={'name': 'Caixa físico'})[0]

    def open(self, amount='100', **changes):
        body = {'account_id': self.cash_account().pk, 'amount': amount, 'note': '', 'request_id': str(uuid4())}
        body.update(changes)
        response = self.client.post(f'/api/me/cash/?store_id={self.store.pk}', body, format='json')
        return response, body

    def move(self, session, kind='supply', amount='10', reason='Troco', request_id=None):
        return self.client.post(f'/api/me/cash/{session}/postings/?store_id={self.store.pk}', {'kind': kind, 'amount': amount, 'reason': reason, 'request_id': request_id or str(uuid4())}, format='json')

    def close(self, session, counted='100', note='', request_id=None):
        return self.client.post(f'/api/me/cash/{session}/close/?store_id={self.store.pk}', {'counted_amount': counted, 'note': note, 'request_id': request_id or str(uuid4())}, format='json')

    def cash_sale(self, *, amount='700', confirmed=True):
        body = self.data(kind='cash', amount=amount, confirmed=confirmed)
        body['payments'][0]['account_id'] = self.cash_account().pk
        return self.client.post(self.url, body, format='json'), body

    def test_open_zero_and_idempotent_retry(self):
        response, body = self.open('0')
        self.assertEqual(response.status_code, 200, response.data)
        retry = self.client.post(f'/api/me/cash/?store_id={self.store.pk}', body, format='json')
        self.assertEqual(retry.data['id'], response.data['id'])
        self.assertEqual(CashSession.objects.count(), 1)
        self.assertEqual(CashPosting.objects.count(), 0)
        self.assertEqual(FinancialEntry.objects.count(), 0)
        self.assertEqual(response.data['expected_cash'], '0.00')

    def test_payment_options_report_control_and_current_opening(self):
        account = self.cash_account()
        url = f'/api/me/sales/payment-options/?store_id={self.store.pk}'
        def option():
            return next(item for item in self.client.get(url).data['accounts'] if item['id'] == account.pk)
        self.assertFalse(option()['cash_control_enabled'])
        session = self.open()[0].data['id']
        self.assertTrue(option()['cash_control_enabled'])
        self.assertTrue(option()['cash_is_open'])
        self.close(session)
        self.assertTrue(option()['cash_control_enabled'])
        self.assertFalse(option()['cash_is_open'])

    def test_second_open_of_same_account_is_denied(self):
        self.assertEqual(self.open()[0].status_code, 200)
        self.assertEqual(self.open()[0].status_code, 400)
        self.assertEqual(CashSession.objects.count(), 1)

    def test_open_different_cash_accounts(self):
        self.open()
        other = FinancialAccount.objects.create(store=self.store, code='cash2', name='Caixa 2', is_cash_box=True)
        self.assertEqual(self.open(account_id=other.pk)[0].status_code, 200)
        self.assertEqual(CashSession.objects.count(), 2)

    def test_open_bank_or_other_unit_or_inactive_denied(self):
        for account in [self.account, self.other_account]:
            self.assertEqual(self.open(account_id=account.pk)[0].status_code, 400)
        cash = self.cash_account(); cash.is_active = False; cash.save()
        self.assertEqual(self.open()[0].status_code, 400)

    def test_money_receipt_matches_financial_without_double_recording(self):
        response, _ = self.open(); session = response.data['id']
        sale, body = self.cash_sale()
        self.assertEqual(sale.status_code, 200, sale.data)
        self.assertEqual(CashSession.objects.get(pk=session).expected_cash, Decimal('800'))
        self.assertEqual(FinancialEntry.objects.count(), 1)
        self.assertEqual(CashPosting.objects.count(), 1)
        retry = self.client.post(self.url, body, format='json')
        self.assertEqual(retry.status_code, 200, retry.data)
        self.assertEqual(CashPosting.objects.count(), 1)
        self.assertEqual(self.cash_account().balance, Decimal('700'))

    def test_pix_on_same_account_is_not_physical_cash(self):
        response, _ = self.open(); body = self.data()
        body['payments'][0]['account_id'] = self.cash_account().pk
        sale = self.client.post(self.url, body, format='json')
        self.assertEqual(sale.status_code, 200, sale.data)
        self.assertEqual(CashPosting.objects.count(), 0)
        self.assertEqual(CashSession.objects.get(pk=response.data['id']).expected_cash, Decimal('100'))

    def test_unconfirmed_cash_does_not_enter_cash_until_received(self):
        response, _ = self.open()
        sale, _ = self.cash_sale(confirmed=False)
        self.assertEqual(sale.status_code, 200, sale.data)
        self.assertEqual(CashPosting.objects.count(), 0)
        self.client.force_authenticate(self.admin)
        receivable = Receivable.objects.get()
        result = self.client.post(f'/api/me/receivables/{receivable.pk}/receive/?store_id={self.store.pk}', {'request_id': str(uuid4()), 'amount': '50', 'account_id': self.cash_account().pk, 'method_id': self.methods['cash'].pk}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(CashSession.objects.get(pk=response.data['id']).expected_cash, Decimal('150'))

    def test_manual_movements_require_reason_and_sufficient_cash(self):
        session = self.open()[0].data['id']
        self.assertEqual(self.move(session, reason='').status_code, 400)
        self.assertEqual(self.move(session, amount='0').status_code, 400)
        self.assertEqual(self.move(session, kind='withdrawal', amount='101').status_code, 400)
        self.assertEqual(self.move(session, amount='20').status_code, 200)
        self.assertEqual(self.move(session, kind='withdrawal', amount='15').status_code, 200)
        self.assertEqual(CashSession.objects.get(pk=session).expected_cash, Decimal('105'))
        self.assertEqual(FinancialEntry.objects.count(), 0)

    def test_movement_retries_and_changed_payload(self):
        session = self.open()[0].data['id']; identity = str(uuid4())
        self.assertEqual(self.move(session, request_id=identity).status_code, 200)
        self.assertEqual(self.move(session, request_id=identity).status_code, 200)
        self.assertEqual(self.move(session, amount='11', request_id=identity).status_code, 400)
        self.assertEqual(CashPosting.objects.count(), 1)

    def test_close_counts_difference_and_requires_justification(self):
        session = self.open()[0].data['id']
        self.assertEqual(self.close(session, counted='98').status_code, 400)
        response = self.close(session, counted='98', note='Faltam dois reais no troco')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['difference'], '-2.00')
        self.assertEqual(response.data['expected_cash'], '100.00')
        self.assertEqual(FinancialEntry.objects.count(), 0)

    def test_matching_close_and_repeat_are_preserved(self):
        session = self.open()[0].data['id']; identity = str(uuid4())
        self.assertEqual(self.close(session, request_id=identity).status_code, 200)
        self.assertEqual(self.close(session, request_id=identity).status_code, 200)
        self.assertEqual(self.close(session, counted='101', note='Outro', request_id=identity).status_code, 400)
        self.assertEqual(self.move(session).status_code, 400)
        self.assertEqual(self.open()[0].status_code, 200)

    def test_closed_account_blocks_cash_sale_atomically(self):
        session = self.open()[0].data['id']; self.close(session)
        sale, _ = self.cash_sale()
        self.assertEqual(sale.status_code, 400, sale.data)
        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)
        self.assertEqual(Receivable.objects.count(), 0)
        self.assertEqual(FinancialEntry.objects.count(), 0)

    def test_cancellation_posts_refund_to_current_session(self):
        first = self.open()[0].data['id']
        sale, _ = self.cash_sale()
        self.assertEqual(sale.status_code, 200, sale.data)
        self.close(first, counted='800')
        second = self.open('800')[0].data['id']
        self.client.force_authenticate(self.admin)
        cancel = self.client.post(f'/api/me/sales/{sale.data["id"]}/cancel/?store_id={self.store.pk}', {'reason': 'Devolução'}, format='json')
        self.assertEqual(cancel.status_code, 200, cancel.data)
        self.assertEqual(CashSession.objects.get(pk=first).expected_cash, Decimal('800'))
        self.assertEqual(CashSession.objects.get(pk=second).expected_cash, Decimal('100'))
        self.assertEqual(CashPosting.objects.get(kind='refund').session_id, second)

    def test_refund_without_cash_or_sufficient_balance_rolls_back_cancellation(self):
        session = self.open('0')[0].data['id']; sale, _ = self.cash_sale()
        self.move(session, kind='withdrawal', amount='700')
        self.client.force_authenticate(self.admin)
        url = f'/api/me/sales/{sale.data["id"]}/cancel/?store_id={self.store.pk}'
        response = self.client.post(url, {'reason': 'Devolução'}, format='json')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(Sale.objects.get(pk=sale.data['id']).status, 'completed')
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertEqual(FinancialEntry.objects.count(), 1)

    def test_non_owner_staff_needs_explicit_permission(self):
        session = self.open()[0].data['id']; self.client.force_authenticate(self.admin)
        self.assertEqual(self.move(session).status_code, 403)
        self.assertEqual(self.close(session).status_code, 403)
        self.admin.user_permissions.add(Permission.objects.get(codename='manage_cash'))
        self.admin = type(self.admin).objects.get(pk=self.admin.pk); self.client.force_authenticate(self.admin)
        self.assertEqual(self.move(session).status_code, 200)
        self.assertEqual(self.close(session, counted='110').status_code, 200)

    def test_cross_unit_anonymous_and_csrf_denied(self):
        session = self.open()[0].data['id']
        self.assertEqual(self.client.get(f'/api/me/cash/{session}/?store_id={self.other.pk}').status_code, 400)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f'/api/me/cash/?store_id={self.store.pk}').status_code, 403)
        browser = APIClient(enforce_csrf_checks=True); browser.force_login(self.user)
        self.assertEqual(browser.post(f'/api/me/cash/?store_id={self.store.pk}', {'account_id': self.cash_account().pk, 'amount': '0', 'request_id': str(uuid4())}, format='json').status_code, 403)

    def test_history_and_admin_are_read_only(self):
        session = CashSession.objects.get(pk=self.open()[0].data['id']); posting_id = self.move(session.pk).data['id']
        with self.assertRaises(ValidationError): session.delete()
        with self.assertRaises(ValidationError): session.save()
        posting = CashPosting.objects.get(pk=posting_id)
        with self.assertRaises(ValidationError): posting.save()
        with self.assertRaises(ValidationError): posting.delete()
        self.assertFalse(admin.site._registry[CashSession].has_change_permission(None))
        self.assertEqual(self.client.patch(f'/api/me/cash/{session.pk}/?store_id={self.store.pk}', {}, format='json').status_code, 405)

    def test_legacy_cash_entries_are_not_backfilled(self):
        sale, _ = self.cash_sale()
        self.assertEqual(sale.status_code, 200, sale.data)
        self.assertEqual(CashPosting.objects.count(), 0)
        session = self.open('700')[0].data['id']
        self.assertEqual(CashPosting.objects.count(), 0)
        self.assertEqual(CashSession.objects.get(pk=session).expected_cash, Decimal('700'))

    def test_failure_writing_cash_posting_rolls_back_sale(self):
        self.open()
        with patch('sales.cash_services.CashPosting.objects.create', side_effect=ValidationError('Falha simulada')):
            response, _ = self.cash_sale()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(FinancialEntry.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_ledger_is_paginated_and_scoped(self):
        session = self.open()[0].data['id']
        for number in range(26): self.move(session, reason=f'Movimento {number}')
        first = self.client.get(f'/api/me/cash/{session}/postings/?store_id={self.store.pk}')
        second = self.client.get(f'/api/me/cash/{session}/postings/?store_id={self.store.pk}&page=2')
        self.assertEqual(first.data['count'], 26)
        self.assertEqual(len(first.data['results']), 25)
        self.assertEqual(len(second.data['results']), 1)

    def test_invalid_open_and_forged_operator_are_not_accepted(self):
        self.assertEqual(self.open('-1')[0].status_code, 400)
        response, _ = self.open(opened_by=self.admin.pk, closing_expected='900')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['opened_by'], self.user.pk)
        self.assertEqual(response.data['expected_cash'], '100.00')


from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import TransactionTestCase, skipUnlessDBFeature
from .cash_services import open_cash, move_cash, close_cash
from .payment_services import receive_installment


class CashConcurrencyTests(TransactionTestCase):
    setUp = fixtures.PaymentCheckoutTests.setUp
    data = fixtures.PaymentCheckoutTests.data
    cash_account = CashTests.cash_account
    cash_sale = CashTests.cash_sale

    def parallel(self, functions):
        barrier = Barrier(2)
        def run(function):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try: return ('ok', function())
                except ValidationError: return ('denied', None)
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run, functions))

    @skipUnlessDBFeature('has_select_for_update')
    def test_simultaneous_open_retry_creates_one_session(self):
        account = self.cash_account(); identity = uuid4()
        def operation():
            return open_cash(user=get_user_model().objects.get(pk=self.user.pk), store=self.store, account_id=account.pk, amount=Decimal('100'), note='', request_id=identity).pk
        results = self.parallel([operation, operation])
        self.assertEqual(results[0], results[1])
        self.assertEqual(CashSession.objects.count(), 1)

    @skipUnlessDBFeature('has_select_for_update')
    def test_concurrent_withdrawals_cannot_overdraw_physical_cash(self):
        session = open_cash(user=self.user, store=self.store, account_id=self.cash_account().pk, amount=Decimal('100'), note='', request_id=uuid4())
        def operation():
            return move_cash(user=get_user_model().objects.get(pk=self.user.pk), store=self.store, session_id=session.pk, kind='withdrawal', amount=Decimal('80'), reason='Retirada', request_id=uuid4()).pk
        results = self.parallel([operation, operation])
        self.assertEqual(sorted(result[0] for result in results), ['denied', 'ok'])
        self.assertEqual(CashPosting.objects.count(), 1)
        self.assertEqual(CashSession.objects.get(pk=session.pk).expected_cash, Decimal('20'))

    @skipUnlessDBFeature('has_select_for_update')
    def test_receipt_and_close_serialize_without_changing_closed_snapshot(self):
        account = self.cash_account()
        session = open_cash(user=self.user, store=self.store, account_id=account.pk, amount=Decimal('0'), note='', request_id=uuid4())
        response, _ = self.cash_sale(confirmed=False)
        self.assertEqual(response.status_code, 200, response.data)
        receivable = Receivable.objects.get()
        def receipt():
            return receive_installment(user=get_user_model().objects.get(pk=self.admin.pk), store=self.store, receivable_id=receivable.pk, account=account, method=self.methods['cash'], amount=Decimal('50'), request_id=uuid4()).pk
        def close():
            return close_cash(user=get_user_model().objects.get(pk=self.user.pk), store=self.store, session_id=session.pk, counted_amount=Decimal('0'), note='Conferência simultânea', request_id=uuid4()).pk
        results = self.parallel([receipt, close])
        self.assertEqual(results[1][0], 'ok')
        session.refresh_from_db()
        self.assertIsNotNone(session.closed_at)
        total = sum(CashPosting.objects.values_list('amount', flat=True), Decimal('0'))
        self.assertEqual(session.closing_expected, total)
        self.assertIn(total, [Decimal('0'), Decimal('50')])
