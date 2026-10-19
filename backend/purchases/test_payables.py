from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4
from unittest import skipUnless
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import connection, close_old_connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient
from sales.models import FinancialAccount, CashSession, CashPosting, FinancialEntry
from sales.cash_services import open_cash, close_cash
from organizations.models import Store, StockMovement
from . import tests as purchase_fixtures
from .models import PayablePlan, PayableInstallment, PayablePayment
from .payable_services import pay_installment, reverse_payment


class PayablesTests(TestCase):
    def setUp(self):
        purchase_fixtures.PurchaseTests.setUp(self)
        purchase_fixtures.PurchaseTests.grant(self)
        record = purchase_fixtures.PurchaseTests.write(self, purchase_fixtures.PurchaseTests.data(self, items=[{'product_id': self.product.pk, 'quantity': '1', 'unit_cost': '100.01'}]))
        self.purchase_id = record['id']
        purchase_fixtures.PurchaseTests.action(self, record)
        self.grant_payables()
        self.cash = FinancialAccount.objects.create(store=self.store, code='cash', name='Caixa')

    path = purchase_fixtures.PurchaseTests.path
    write = purchase_fixtures.PurchaseTests.write

    def grant_payables(self, user=None, codes=None):
        user = user or self.user
        codes = codes or ['view_payableplan', 'add_payableplan', 'pay_payable', 'reverse_payable', 'view_purchase']
        user.user_permissions.add(*Permission.objects.filter(content_type__app_label='purchases', codename__in=codes))
        for key in ('_perm_cache', '_user_perm_cache', '_group_perm_cache'):
            if hasattr(user, key): delattr(user, key)

    def payable_url(self, suffix='', store=None):
        return f'/api/me/payables/{suffix}?store_id={(store or self.store).pk}'

    def post(self, suffix, data, expected=200, store=None):
        response = self.client.post(self.payable_url(suffix, store), data, format='json')
        self.assertEqual(response.status_code, expected, response.data)
        return response.data

    def plan_data(self, **extra):
        return {'request_id': str(uuid4()), 'purchase_id': self.purchase_id, 'installment_count': 3, 'first_due_date': '2026-01-31', 'interval_unit': 'months', 'interval_count': 1, **extra}

    def plan(self, **extra): return self.post('', self.plan_data(**extra))

    def pay_data(self, **extra):
        return {'request_id': str(uuid4()), 'account_id': self.account.pk, 'method_id': self.methods['pix'].pk, 'amount': '10.00', 'paid_on': str(timezone.localdate()), 'reason': 'Comprovante de teste', **extra}

    def pay(self, installment, data=None, expected=200):
        return self.post(f'installments/{installment}/pay/', data or self.pay_data(), expected)

    def reverse(self, payment, data=None, expected=200):
        return self.post(f'payments/{payment}/reverse/', data or {'request_id': str(uuid4()), 'reason': 'Correção de lançamento'}, expected)

    def test_exact_schedule_preserves_total_and_month_end(self):
        plan = self.plan()
        self.assertEqual([i['amount'] for i in plan['installments']], ['33.34', '33.34', '33.33'])
        self.assertEqual([str(i['due_date']) for i in plan['installments']], ['2026-01-31', '2026-02-28', '2026-03-31'])
        self.assertEqual(plan['remaining'], '100.01')
        self.assertEqual(PayablePayment.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertEqual(self.account.balance, Decimal('0.00'))

    def test_plan_retry_and_conflicting_id_or_second_plan(self):
        data = self.plan_data(); first = self.post('', data)
        self.assertEqual(first['id'], self.post('', data)['id'])
        self.post('', {**data, 'installment_count': 2}, 400)
        self.post('', self.plan_data(), 400)
        self.assertEqual(PayablePlan.objects.count(), 1)

    def test_draft_cancelled_and_zero_purchase_rejected(self):
        record = purchase_fixtures.PurchaseTests.write(self, purchase_fixtures.PurchaseTests.data(self, reference='ZERO', items=[{'product_id': self.product.pk, 'quantity': '1', 'unit_cost': '0'}]))
        self.post('', self.plan_data(purchase_id=record['id']), 400)
        purchase_fixtures.PurchaseTests.action(self, record)
        self.post('', self.plan_data(purchase_id=record['id']), 400)
        self.assertFalse(PayablePlan.objects.exists())

    def test_partial_payment_and_reversal_restore_debt_and_bank(self):
        plan = self.plan(); installment = plan['installments'][0]['id']
        paid = self.pay(installment)
        self.assertEqual(paid['paid'], '10.00'); self.assertEqual(paid['remaining'], '90.01')
        self.assertEqual(self.account.balance, Decimal('-10'))
        payment = PayablePayment.objects.get()
        result = self.reverse(payment.pk)
        self.assertEqual(result['remaining'], '100.01'); self.assertEqual(self.account.balance, Decimal('0'))
        self.assertEqual(PayablePayment.objects.count(), 2)
        self.assertEqual(FinancialEntry.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_payment_retry_and_changed_payload(self):
        plan = self.plan(); installment = plan['installments'][0]['id']; data = self.pay_data()
        self.pay(installment, data); self.pay(installment, data)
        self.pay(installment, {**data, 'amount': '11'}, 400)
        self.assertEqual(PayablePayment.objects.count(), 1)

    def test_full_payment_paid_filter_and_overpayment(self):
        plan = self.plan(installment_count=1); installment = plan['installments'][0]['id']
        self.pay(installment, self.pay_data(amount='100.02'), 400)
        result = self.pay(installment, self.pay_data(amount='100.01'))
        self.assertEqual(result['status'], 'paid')
        self.pay(installment, expected=400)
        self.assertEqual(self.client.get(self.payable_url()+'&status=paid').data['count'], 1)
        self.assertEqual(self.client.get(self.payable_url()+'&status=pending').data['count'], 0)

    def test_reversal_retry_and_second_reversal_rejected(self):
        plan = self.plan(); self.pay(plan['installments'][0]['id'])
        payment = PayablePayment.objects.get(); data = {'request_id': str(uuid4()), 'reason': 'Correção'}
        self.reverse(payment.pk, data); self.reverse(payment.pk, data)
        self.reverse(payment.pk, expected=400)
        self.reverse(PayablePayment.objects.get(reversal_of=payment).pk, expected=400)
        self.assertEqual(PayablePayment.objects.count(), 2)

    def test_inactive_bank_and_method_can_be_reversed_historically(self):
        plan = self.plan(); self.pay(plan['installments'][0]['id'])
        self.account.is_active = False; self.account.save()
        self.methods['pix'].is_active = False; self.methods['pix'].save()
        self.reverse(PayablePayment.objects.get().pk)
        self.assertEqual(self.account.balance, Decimal('0'))

    def test_cash_requires_open_owner_and_sufficient_funds(self):
        plan = self.plan(); installment = plan['installments'][0]['id']
        data = self.pay_data(account_id=self.cash.pk, method_id=self.methods['cash'].pk)
        self.pay(installment, data, 400)
        session = open_cash(user=self.user, store=self.store, account_id=self.cash.pk, amount=Decimal('5'), note='', request_id=uuid4())
        self.pay(installment, data, 400)
        self.assertEqual(CashPosting.objects.count(), 0)
        self.assertEqual(PayablePayment.objects.count(), 0)
        self.grant_payables(self.admin); self.client.force_authenticate(self.admin)
        self.pay(installment, self.pay_data(amount='1', account_id=self.cash.pk, method_id=self.methods['cash'].pk), 403)
        self.client.force_authenticate(self.user)
        self.pay(installment, self.pay_data(amount='5', account_id=self.cash.pk, method_id=self.methods['cash'].pk))
        self.assertEqual(session.expected_cash, Decimal('0'))

    def test_cash_posting_replay_closed_session_and_new_session_reversal(self):
        plan = self.plan(); installment = plan['installments'][0]['id']
        session = open_cash(user=self.user, store=self.store, account_id=self.cash.pk, amount=Decimal('20'), note='', request_id=uuid4())
        data = self.pay_data(account_id=self.cash.pk, method_id=self.methods['cash'].pk)
        self.pay(installment, data); payment = PayablePayment.objects.get()
        self.pay(installment, data)
        self.assertEqual(CashPosting.objects.count(), 1); self.assertEqual(session.expected_cash, Decimal('10'))
        close_cash(user=self.user, store=self.store, session_id=session.pk, counted_amount=Decimal('10'), note='', request_id=uuid4())
        self.pay(installment, data)  # Replay continua válido após fechar.
        self.reverse(payment.pk, expected=400)
        new = open_cash(user=self.user, store=self.store, account_id=self.cash.pk, amount=Decimal('0'), note='', request_id=uuid4())
        self.reverse(payment.pk)
        session.refresh_from_db(); self.assertEqual(session.expected_cash, Decimal('10'))
        self.assertEqual(new.expected_cash, Decimal('10')); self.assertEqual(CashPosting.objects.count(), 2)
        ledger = self.client.get(f'/api/me/cash/{new.pk}/postings/?store_id={self.store.pk}').data['results'][0]
        self.assertEqual(ledger['kind_label'], 'Estorno de pagamento a fornecedor'); self.assertEqual(ledger['purchase_id'], self.purchase_id)

    def test_failure_rolls_back_cash_posting_and_payment(self):
        plan = self.plan(); installment = plan['installments'][0]['id']
        session = open_cash(user=self.user, store=self.store, account_id=self.cash.pk, amount=Decimal('20'), note='', request_id=uuid4())
        with patch.object(PayablePayment, 'save', side_effect=ValidationError('Falha simulada')):
            self.pay(installment, self.pay_data(account_id=self.cash.pk, method_id=self.methods['cash'].pk), 400)
        self.assertEqual(session.expected_cash, Decimal('20')); self.assertFalse(CashPosting.objects.exists()); self.assertFalse(PayablePayment.objects.exists())

    def test_account_method_unit_cash_pairing_active_and_future_date(self):
        plan = self.plan(); installment = plan['installments'][0]['id']
        for extra in [{'account_id': self.other_account.pk}, {'account_id': self.cash.pk}, {'method_id': self.methods['cash'].pk}, {'method_id': self.methods['credit'].pk}, {'paid_on': str(timezone.localdate()+timedelta(days=1))}]:
            self.pay(installment, self.pay_data(**extra), 404 if extra.get('account_id') == self.other_account.pk else 400)
        self.account.is_active=False; self.account.save()
        self.pay(installment, expected=404)
        self.assertFalse(PayablePayment.objects.exists())

    def test_backdated_bank_payment_allowed_cash_must_be_today(self):
        plan = self.plan(); installment = plan['installments'][0]['id']; past=str(timezone.localdate()-timedelta(days=1))
        self.pay(installment, self.pay_data(paid_on=past))
        self.pay(installment, self.pay_data(paid_on=past, account_id=self.cash.pk, method_id=self.methods['cash'].pk), 400)

    def test_cross_unit_and_foreign_uuid_are_rejected(self):
        plan = self.plan()
        self.assertEqual(self.client.get(self.payable_url(f'{plan["id"]}/',self.other)).status_code,400)
        from accounts.models import StoreMembership
        StoreMembership.objects.create(user=self.user, store=self.other, role=StoreMembership.Role.SELLER)
        self.assertEqual(self.client.get(self.payable_url(f'{plan["id"]}/',self.other)).status_code,404)
        self.assertEqual(self.client.get(self.payable_url(store=self.other)).data['count'],0)
        data = self.pay_data(); installment=plan['installments'][0]['id']; self.pay(installment,data)
        self.grant_payables(self.admin); self.client.force_authenticate(self.admin)
        self.pay(installment,data,403)
        self.pay(installment,expected=200)  # Permissão explícita + vínculo permite operar.

    def test_staff_permissions_anonymous_and_csrf(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(self.payable_url()).status_code,403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.payable_url()).status_code,403)
        client=APIClient(enforce_csrf_checks=True);client.force_login(self.user)
        self.assertEqual(client.post(self.payable_url(),self.plan_data(),format='json').status_code,403)
        self.assertFalse(PayablePlan.objects.exists())

    def test_invalid_schedule_and_payment_values(self):
        for extra in [{'installment_count':0},{'installment_count':13},{'interval_count':13},{'first_due_date':'9999-12-31'}]:self.post('',self.plan_data(**extra),400)
        plan=self.plan();installment=plan['installments'][0]['id']
        for value in ['0','-1','1.001','NaN','Infinity']:self.pay(installment,self.pay_data(amount=value),400)
        self.pay(installment,self.pay_data(reason=' '),400)
        self.assertFalse(PayablePayment.objects.exists())

    def test_customer_receipts_and_supplier_payments_keep_separate_balances(self):
        from sales import test_payments as receipt_fixtures
        from sales.models import Receivable
        response = self.client.post(self.url, receipt_fixtures.PaymentCheckoutTests.data(self), format='json')
        self.assertEqual(response.status_code, 200, response.data)
        receivable = Receivable.objects.get()
        self.assertEqual(receivable.paid_amount, Decimal('700'))
        self.assertEqual(self.account.balance, Decimal('700'))
        plan = self.plan(); self.pay(plan['installments'][0]['id'])
        self.assertEqual(receivable.paid_amount, Decimal('700'))
        self.assertEqual(self.account.balance, Decimal('690'))
        self.reverse(PayablePayment.objects.get().pk)
        self.assertEqual(receivable.paid_amount, Decimal('700'))
        self.assertEqual(self.account.balance, Decimal('700'))

    def test_view_permission_alone_does_not_allow_writes(self):
        plan = self.plan()
        self.grant_payables(self.admin, ['view_payableplan'])
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(self.payable_url()).status_code, 200)
        self.pay(plan['installments'][0]['id'], expected=403)
        self.post('', self.plan_data(), 403)
        self.assertFalse(PayablePayment.objects.exists())
        self.assertEqual(self.client.post(self.payable_url(f'{plan["id"]}/'), {}, format='json').status_code,405)
        self.assertEqual(self.client.post(self.payable_url('options/'), {}, format='json').status_code,405)

    def test_filters_options_and_immutable_history(self):
        plan=self.plan();self.assertEqual(self.client.get(self.payable_url()+'&status=overdue').data['count'],1)
        self.assertEqual(self.client.get(self.payable_url()+'&purchase_id=invalid').status_code,400)
        self.assertEqual(self.client.get(self.payable_url()+'&status=invalid').status_code,400)
        options=self.client.get(self.payable_url('options/')).data
        self.assertNotIn('credit',[m['kind'] for m in options['methods']])
        self.assertNotIn(self.other_account.pk,[a['id'] for a in options['accounts']])
        self.pay(plan['installments'][0]['id'])
        for record in [PayablePlan.objects.get(),PayableInstallment.objects.first(),PayablePayment.objects.get()]:
            with self.assertRaises(ValidationError):record.save(_service=True)
            with self.assertRaises(ValidationError):record.delete()
        self.assertEqual(self.client.delete(self.payable_url(f'{plan["id"]}/')).status_code,405)


@skipUnless(connection.vendor=='postgresql','Teste de locks exige PostgreSQL.')
class PayablesConcurrencyTests(TransactionTestCase):
    setUp=PayablesTests.setUp
    path=PayablesTests.path
    write=PayablesTests.write
    grant_payables=PayablesTests.grant_payables
    payable_url=PayablesTests.payable_url
    post=PayablesTests.post
    plan_data=PayablesTests.plan_data
    plan=PayablesTests.plan
    pay_data=PayablesTests.pay_data
    pay=PayablesTests.pay

    def worker(self, uid, installment_id, values, reversal=False):
        close_old_connections()
        try:
            user=get_user_model().objects.get(pk=uid);store=Store.objects.get(pk=self.store.pk)
            if reversal:return reverse_payment(user=user,store=store,payment_id=installment_id,values=values).pk
            return pay_installment(user=user,store=store,installment_id=installment_id,values=values).pk
        except ValidationError:return None
        finally:close_old_connections()

    def test_simultaneous_payments_cannot_overpay(self):
        plan=self.plan(installment_count=1);self.grant_payables(self.admin)
        values=[self.pay_data(amount='80') for _ in range(2)]
        from uuid import UUID
        for value in values:value['request_id']=UUID(value['request_id']);value['amount']=Decimal(value['amount']);value['paid_on']=date.fromisoformat(value['paid_on'])
        with ThreadPoolExecutor(max_workers=2) as pool:ids=list(pool.map(lambda pair:self.worker(pair[0],plan['installments'][0]['id'],pair[1]),zip([self.user.pk,self.admin.pk],values)))
        self.assertEqual(sum(i is not None for i in ids),1);self.assertEqual(PayablePayment.objects.count(),1)

    def test_simultaneous_reversals_create_one_counterentry(self):
        plan=self.plan();self.pay(plan['installments'][0]['id']);payment=PayablePayment.objects.get();self.grant_payables(self.admin)
        with ThreadPoolExecutor(max_workers=2) as pool:ids=list(pool.map(lambda uid:self.worker(uid,payment.pk,{'request_id':uuid4(),'reason':'Correção'},True),[self.user.pk,self.admin.pk]))
        self.assertEqual(sum(i is not None for i in ids),1);self.assertEqual(PayablePayment.objects.count(),2)
