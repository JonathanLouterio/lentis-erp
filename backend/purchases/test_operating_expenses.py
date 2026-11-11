from datetime import datetime, timedelta, timezone as utc_timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import StoreMembership
from organizations.models import Company, StockMovement, Store
from purchases.models import ExpenseCancellation, PayablePayment, PayablePlan, Purchase
from sales.cash_services import open_cash
from sales.models import CashPosting, FinancialAccount, PaymentMethod


class OperatingExpenseTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='financeiro')
        company = Company.objects.create(name='Ótica teste')
        self.store = Store.objects.create(company=company, code='01', name='Matriz')
        self.other = Store.objects.create(company=company, code='02', name='Filial')
        for store in (self.store, self.other):
            StoreMembership.objects.create(user=self.user, store=store, role='manager')
        self.bank = FinancialAccount.objects.create(store=self.store, code='bank', name='Banco')
        self.pix = PaymentMethod.objects.create(store=self.store, code='pix', kind='pix', name='Pix')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.grant('purchases', 'view_payableplan', 'add_operating_expense', 'cancel_operating_expense', 'pay_payable', 'reverse_payable')

    def grant(self, app, *codes):
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label=app, codename__in=codes))

    def post(self, suffix, body, expected=200, store=None):
        response = self.client.post(f'/api/me/payables/{suffix}?store_id={(store or self.store).pk}', body, format='json')
        self.assertEqual(response.status_code, expected, response.data)
        return response.data

    def data(self, **fields):
        return dict(request_id=str(uuid4()), category='financing', description='Financiamento do equipamento',
                    payee='Banco do contrato', reference='Contrato 42', total='100.01', installment_count=3,
                    first_due_date='2026-01-31', **fields)

    def cancellation(self, reason='Lançamento duplicado'):
        return {'request_id': str(uuid4()), 'reason': reason}

    def payment(self, amount='10.00'):
        return {'request_id': str(uuid4()), 'account_id': self.bank.pk, 'method_id': self.pix.pk,
                'amount': amount, 'paid_on': str(timezone.localdate()), 'reason': 'Comprovante QA'}

    def rows(self, **filters):
        response = self.client.get('/api/me/payables/', {'store_id': self.store.pk, **filters})
        self.assertEqual(response.status_code, 200, response.data)
        return response.data['results']

    def test_expense_schedule_filters_and_idempotency_without_inventory_or_cash(self):
        data = self.data()
        plan = self.post('expenses/', data)
        self.assertEqual(plan['id'], self.post('expenses/', data)['id'])
        self.post('expenses/', {**data, 'description': 'Alterada'}, 400)
        self.assertIsNone(plan['purchase_id'])
        self.assertEqual((plan['source'], plan['category_label'], plan['payee']), ('expense', 'Financiamento', 'Banco do contrato'))
        self.assertEqual([str(i['due_date']) for i in plan['installments']], ['2026-01-31', '2026-02-28', '2026-03-31'])
        self.assertEqual([i['amount'] for i in plan['installments']], ['33.34', '33.34', '33.33'])
        self.assertEqual([r['id'] for r in self.rows(source='expense', category='financing')], [plan['id']])
        self.assertEqual(self.rows(source='purchase'), [])
        self.assertFalse(Purchase.objects.exists())
        self.assertFalse(StockMovement.objects.exists())
        self.assertFalse(CashPosting.objects.exists())
        self.assertFalse(PayablePayment.objects.exists())
        self.assertEqual(self.bank.balance, Decimal('0'))

    def test_partial_payment_reversal_and_audited_cancellation(self):
        plan = self.post('expenses/', self.data())
        cancel_path = f'expenses/{plan["id"]}/cancel/'
        pay_path = f'installments/{plan["installments"][0]["id"]}/pay/'
        paid = self.post(pay_path, self.payment())
        self.assertEqual(paid['remaining'], '90.01')
        self.assertEqual(paid['installments'][0]['remaining'], '23.34')
        self.assertEqual(self.bank.balance, Decimal('-10'))
        self.post(cancel_path, self.cancellation(), 400)
        payment = paid['installments'][0]['payments'][0]['id']
        self.post(f'payments/{payment}/reverse/', self.cancellation('Correção da baixa'))
        body = self.cancellation()
        cancelled = self.post(cancel_path, body)
        self.assertEqual(self.post(cancel_path, body)['id'], plan['id'])
        self.assertEqual(ExpenseCancellation.objects.count(), 1)
        self.assertEqual((cancelled['status'], cancelled['remaining']), ('cancelled', '0.00'))
        self.assertEqual(cancelled['cancellation']['creator_username'], self.user.username)
        self.assertEqual(cancelled['cancellation']['reason'], body['reason'])
        self.assertEqual(len(cancelled['installments'][0]['payments']), 2)
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.rows(status='overdue'), [])
        self.assertEqual(self.rows(status='cancelled')[0]['id'], plan['id'])
        self.post(pay_path, self.payment(), 400)
        self.assertEqual(self.bank.balance, Decimal('0'))

    def test_store_boundaries_and_explicit_permissions(self):
        plan = self.post('expenses/', self.data())
        pay_path = f'installments/{plan["installments"][0]["id"]}/pay/'
        self.post(pay_path, self.payment(), 404, self.other)
        self.post(f'expenses/{plan["id"]}/cancel/', self.cancellation(), 404, self.other)
        self.assertEqual(self.rows(store_id=self.other.pk), [])
        self.user.user_permissions.remove(Permission.objects.get(content_type__app_label='purchases', codename='add_operating_expense'))
        self.grant('purchases', 'add_payableplan', 'view_purchase')
        self.post('expenses/', self.data(), 403)

    def test_cash_expense_records_and_reverses_cash_outflow(self):
        self.grant('sales', 'view_cashsession', 'add_cashsession', 'move_cash')
        cash = FinancialAccount.objects.create(store=self.store, code='cash', name='Caixa')
        method = PaymentMethod.objects.create(store=self.store, code='cash', kind='cash', name='Dinheiro')
        session = open_cash(user=self.user, store=self.store, account_id=cash.pk,
                            amount=Decimal('50.00'), note='', request_id=uuid4())
        plan = self.post('expenses/', self.data())
        body = {**self.payment(), 'account_id': cash.pk, 'method_id': method.pk}
        paid = self.post(f'installments/{plan["installments"][0]["id"]}/pay/', body)
        payment = paid['installments'][0]['payments'][0]['id']
        posting = CashPosting.objects.get(payable_payment__pk=payment)
        self.assertEqual((posting.session_id, posting.amount), (session.pk, Decimal('-10.00')))
        self.assertIn(f'Despesa #{plan["id"]}', posting.reason)
        self.post(f'payments/{payment}/reverse/', self.cancellation())
        self.assertEqual(session.expected_cash, Decimal('50.00'))

    def paid_expense(self, **overrides):
        payment = {'account_id': self.bank.pk, 'method_id': self.pix.pk, 'paid_on': str(timezone.localdate()), **overrides}
        return {**self.data(), 'category': 'transport', 'description': 'Uber da loja', 'total': '25.00',
                'installment_count': 1, 'first_due_date': payment['paid_on'], 'payment': payment}

    def test_creates_and_pays_expense_once_with_same_request(self):
        body = self.paid_expense(paid_on=str(timezone.localdate() - timedelta(days=1)))
        plan = self.post('expenses/', body)
        self.assertEqual((plan['status'], plan['paid'], plan['remaining']), ('paid', '25.00', '0.00'))
        self.assertEqual(plan['installments'][0]['payments'][0]['paid_on'].isoformat(), body['payment']['paid_on'])
        self.assertEqual(self.post('expenses/', body)['id'], plan['id'])
        self.post('expenses/', {**body, 'total': '27.00'}, 400)
        self.assertEqual(PayablePlan.objects.count(), 1)
        self.assertEqual(PayablePayment.objects.count(), 1)
        self.assertEqual(self.bank.balance, Decimal('-25.00'))
        self.assertFalse(CashPosting.objects.exists())
        self.assertFalse(StockMovement.objects.exists())
        payment = plan['installments'][0]['payments'][0]['id']
        self.post(f'payments/{payment}/reverse/', self.cancellation())
        self.assertEqual(self.post('expenses/', body)['status'], 'pending')
        self.assertEqual(PayablePayment.objects.count(), 2)
        self.assertEqual(self.bank.balance, Decimal('0.00'))

    def test_create_and_pay_requires_payment_permission_even_on_retry(self):
        body = self.paid_expense()
        self.post('expenses/', body)
        self.user.user_permissions.remove(Permission.objects.get(content_type__app_label='purchases', codename='pay_payable'))
        self.post('expenses/', body, 403)
        self.post('expenses/', self.paid_expense(), 403)
        self.assertEqual(self.post('expenses/', self.data())['status'], 'pending')
        self.assertEqual(PayablePayment.objects.count(), 1)

    def test_invalid_payment_rolls_back_the_expense(self):
        other_bank = FinancialAccount.objects.create(store=self.other, code='bank', name='Outro banco')
        self.post('expenses/', self.paid_expense(account_id=other_bank.pk), 404)
        self.post('expenses/', self.paid_expense(paid_on=str(timezone.localdate() + timedelta(days=1))), 400)
        self.post('expenses/', {**self.paid_expense(), 'installment_count': 2}, 400)
        self.assertFalse(PayablePlan.objects.exists())
        self.assertFalse(PayablePayment.objects.exists())

    def test_cash_payment_requires_permission_open_session_and_balance(self):
        cash = FinancialAccount.objects.create(store=self.store, code='cash', name='Caixa')
        method = PaymentMethod.objects.create(store=self.store, code='cash', kind='cash', name='Dinheiro')
        body = self.paid_expense(account_id=cash.pk, method_id=method.pk)
        self.post('expenses/', body, 403)
        self.grant('sales', 'view_cashsession', 'add_cashsession', 'move_cash')
        self.post('expenses/', body, 400)
        session = open_cash(user=self.user, store=self.store, account_id=cash.pk,
                            amount=Decimal('30.00'), note='', request_id=uuid4())
        self.post('expenses/', {**body, 'total': '31.00'}, 400)
        self.assertFalse(PayablePlan.objects.exists())
        plan = self.post('expenses/', body)
        self.assertEqual(self.post('expenses/', body)['id'], plan['id'])
        self.assertEqual(list(CashPosting.objects.values_list('amount', flat=True)), [Decimal('-25.00')])
        self.assertEqual(session.expected_cash, Decimal('5.00'))
        self.user.user_permissions.remove(Permission.objects.get(content_type__app_label='sales', codename='move_cash'))
        self.post('expenses/', body, 403)
        self.assertEqual(PayablePayment.objects.count(), 1)

    def test_invalid_expenses_do_not_create_titles(self):
        for invalid in ({'description': '  '}, {'total': '0'}, {'total': '0.01'}, {'category': 'unknown'}):
            self.post('expenses/', {**self.data(), **invalid}, 400)
        self.assertFalse(PayablePlan.objects.exists())

    @patch('django.utils.timezone.now', return_value=datetime(2026, 11, 11, 0, 8, tzinfo=utc_timezone.utc))
    def test_reports_include_expenses_and_keep_payments_after_cancellation(self, _clock):
        self.grant('sales', 'view_reports', 'view_financialentry')
        # Após meia-noite em UTC, o registro ainda pertence ao dia anterior em São Paulo.
        today = '2026-11-10'
        plan = self.post('expenses/', {**self.data(), 'first_due_date': today, 'installment_count': 1})
        paid = self.post(f'installments/{plan["installments"][0]["id"]}/pay/', {**self.payment(), 'paid_on': today})
        def report(kind, day=today):
            response = self.client.get('/api/me/reports/', {'store_id': self.store.pk, 'report': kind,
                'start': day, 'end': day, **({'status': 'all'} if kind == 'payables' else {})})
            self.assertEqual(response.status_code, 200, response.data)
            return response.data['results']
        document = f'Despesa #{plan["id"]}'
        self.assertEqual([(r['document'], r['remaining'], r['category']) for r in report('payables')], [(document, '90.01', 'Financiamento')])
        self.assertEqual([(r['document'], r['type'], r['amount'], r['party']) for r in report('movements')],
                         [(document, 'Pagamento de despesa', '-10.00', 'Banco do contrato')])
        self.assertEqual(report('movements', '2026-11-11'), [])
        payment = paid['installments'][0]['payments'][0]['id']
        self.post(f'payments/{payment}/reverse/', self.cancellation())
        self.post(f'expenses/{plan["id"]}/cancel/', self.cancellation())
        self.assertEqual(report('payables'), [])
        self.assertCountEqual([r['amount'] for r in report('movements')], ['-10.00', '10.00'])
