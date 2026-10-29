from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.test import TestCase, SimpleTestCase
from django.contrib.auth.models import Permission
from rest_framework.test import APIClient

from organizations.models import StockMovement
from . import test_payments as fixtures
from .models import Sale, Receivable, FinancialEntry, CheckoutRequest, DiscountPolicy
from .payment_services import complete_sale
from .services import cancel_sale
from .financing import financing_fees, validate_down_payment
from .dashboard_views import sales_for
from .commercial_services import discount_snapshot


class FinancingMathTests(SimpleTestCase):
    def test_entry_rounds_up_to_cent_and_fee_rounds_half_up(self):
        with self.assertRaises(ValidationError):
            validate_down_payment(Decimal('100.01'), [('pix', Decimal('40'), 1, True), ('boleto', Decimal('60.01'), 2, False)])
        self.assertEqual(validate_down_payment(Decimal('100.01'), [('pix', Decimal('40.01'), 1, True), ('boleto', Decimal('60'), 2, False)]), Decimal('40.01'))
        self.assertEqual(financing_fees(Decimal('5'), [('boleto', Decimal('0.10')), ('credit', Decimal('100'))]), [Decimal('.01'), Decimal('0')])

    def test_invalid_rates_are_rejected(self):
        for rate in ['NaN', 'Infinity', '-1', '100.01', '1.001']:
            with self.subTest(rate=rate), self.assertRaises(ValidationError):
                financing_fees(Decimal(rate), [('boleto', Decimal('100'))])


class FinancingTests(TestCase):
    setUp = fixtures.PaymentCheckoutTests.setUp
    data = fixtures.PaymentCheckoutTests.data

    def body(self, *, entry='280', rate='5', kind='store_credit', count=2, confirmed=True, action='complete'):
        body = self.data(action=action, amount=entry, confirmed=confirmed)
        body['financing_rate'] = rate
        body['payments'].append(self.data(kind=kind, amount=str(Decimal('700')-Decimal(entry)), count=count, confirmed=False)['payments'][0])
        return body

    def post(self, body, expected=200):
        response = self.client.post(self.url, body, format='json')
        self.assertEqual(response.status_code, expected, response.data)
        return response

    def preview(self, body, total='700'):
        return self.client.post(f'/api/me/sales/payment-preview/?store_id={self.store.pk}', {'total': total, 'financing_rate': body.get('financing_rate','0'), 'payments': body['payments']}, format='json')

    def test_preview_checkout_receivables_and_dashboard_agree(self):
        body = self.body()
        preview = self.preview(body)
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual(preview.data['total'], '721.00')
        self.assertEqual(preview.data['financing_amount'], '21.00')
        self.assertFalse(Sale.objects.exists())
        response = self.post(body)
        self.assertEqual(response.data['base_total'], '700.00')
        self.assertEqual(response.data['total'], '721.00')
        self.assertEqual(response.data['payments'][1]['principal_amount'], '420.00')
        self.assertEqual(response.data['payments'][1]['amount'], '441.00')
        self.assertEqual([i['amount'] for i in response.data['payments'][1]['installments']], ['220.50', '220.50'])
        self.assertEqual(sum((r.amount for r in Receivable.objects.all()), Decimal('0')), Decimal('721'))
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal('280'))
        self.assertEqual(sales_for(self.store).get(pk=response.data['id']).dashboard_total, Decimal('721'))

    def test_boleto_and_credit_below_minimum_rollback_everything(self):
        for kind in ['boleto', 'store_credit']:
            body=self.body(entry='279.99', kind=kind)
            with self.subTest(kind=kind):
                self.assertEqual(self.preview(body).status_code,400)
                self.post(body,400)
        for model in [Sale, CheckoutRequest, FinancialEntry, Receivable, StockMovement]:
            self.assertEqual(model.objects.count(),0)
        self.product.refresh_from_db(); self.assertEqual(self.product.stock_quantity,Decimal('10'))

    def test_unconfirmed_entry_draft_allowed_but_completion_denied(self):
        response=self.post(self.body(confirmed=False,action='draft'))
        self.assertEqual(response.data['financing_amount'],'21.00')
        with self.assertRaises(ValidationError): complete_sale(user=self.user,sale_id=response.data['id'])
        self.assertFalse(Receivable.objects.exists()); self.assertFalse(StockMovement.objects.exists())

    def test_saved_draft_fee_cannot_be_stale_when_finalized(self):
        response=self.post(self.body(action='draft'))
        sale=Sale.objects.get(pk=response.data['id'])
        sale.financing_rate=Decimal('10');sale.save()
        with self.assertRaises(ValidationError): complete_sale(user=self.user,sale_id=sale.pk)
        self.assertFalse(Receivable.objects.exists())

    def test_no_entry_split_lines_cannot_bypass_rule(self):
        body=self.data(kind='boleto',amount='350',confirmed=False)
        body['payments'].append(dict(body['payments'][0]))
        self.post(body,400)

    def test_one_balance_installment_plus_entry_requires_minimum(self):
        self.post(self.body(entry='200', count=1),400)
        self.post(self.body(entry='280', count=1))

    def test_single_integral_charge_and_card_installments_remain_allowed(self):
        for kind,count in [('boleto',1),('store_credit',1),('credit',3)]:
            self.post(self.data(kind=kind,count=count,confirmed=False))

    def test_rate_rejected_without_financed_balance_and_not_applied_to_card(self):
        body=self.data();body['financing_rate']='5';self.post(body,400)
        body=self.body();body['payments'][1]['amount']='220'
        body['payments'].append(self.data(kind='credit',amount='200',count=2,confirmed=False)['payments'][0])
        result=self.post(body)
        self.assertEqual(result.data['total'],'711.00')
        self.assertEqual(result.data['payments'][2]['financing_amount'],'0.00')

    def test_discount_base_and_entry_are_before_financing(self):
        body=self.body(entry='240')
        body['discount_amount']='100'
        body['payments'][1]['amount']='360'
        result=self.post(body)
        self.assertEqual(result.data['base_total'],'600.00')
        self.assertEqual(result.data['total'],'618.00')
        sale=Sale.objects.get(pk=result.data['id'])
        self.assertEqual(discount_snapshot(sale,self.user)['discount'],Decimal('100'))

    def test_large_fee_does_not_bypass_discount_authorization(self):
        from accounts.models import StoreMembership
        DiscountPolicy.objects.create(store=self.store, role=StoreMembership.Role.SELLER, limit_percentage=Decimal('0'))
        body=self.body(entry='240', rate='100');body['discount_amount']='100';body['payments'][1]['amount']='360'
        self.post(body,400)
        self.assertFalse(StockMovement.objects.exists())

    def test_forged_surcharge_and_totals_are_ignored(self):
        body=self.body();body.update(financing_amount='0',total='700')
        body['payments'][1].update(financing_amount='0',principal_amount='0')
        result=self.post(body)
        self.assertEqual(result.data['total'],'721.00')

    def test_retry_does_not_duplicate_fee_stock_or_money_and_changed_rate_rejected(self):
        body=self.body();first=self.post(body);second=self.post(body)
        self.assertEqual(first.data['id'],second.data['id'])
        self.assertEqual((Sale.objects.count(),Receivable.objects.count(),StockMovement.objects.count(),FinancialEntry.objects.count()),(1,3,1,1))
        body['financing_rate']='6';self.post(body,400)

    def test_edit_draft_replaces_fee_without_compounding(self):
        body=self.body(action='draft');first=self.post(body)
        body.update(sale_id=first.data['id'],request_id=str(uuid4()),financing_rate='10')
        updated=self.post(body)
        self.assertEqual(updated.data['financing_amount'],'42.00')
        self.assertEqual(updated.data['total'],'742.00')
        self.assertEqual(Sale.objects.count(),1)
        sale=complete_sale(user=self.user,sale_id=first.data['id'])
        self.assertEqual(sale.total,Decimal('742'))

    def test_cancellation_preserves_fee_history_and_reverses_actual_entry_only(self):
        response=self.post(self.body())
        sale=cancel_sale(user=self.admin,sale_id=response.data['id'],reason='Teste')
        self.assertEqual(sale.total,Decimal('721'))
        self.account.refresh_from_db();self.assertEqual(self.account.balance,Decimal('0'))
        self.assertEqual(Receivable.objects.count(),3)
        self.assertEqual(FinancialEntry.objects.count(),2)
        self.assertTrue(all(r.status=='cancelled' for r in Receivable.objects.all()))

    def test_receipt_permission_still_required_for_entry(self):
        self.user.user_permissions.remove(Permission.objects.get(content_type__app_label='sales',codename='receive_receivable'))
        self.post(self.body(),403)
        self.post(self.body(action='draft',confirmed=False))
        self.assertFalse(FinancialEntry.objects.exists())

    def test_bad_rate_csrf_and_other_unit_are_rejected(self):
        for rate in ['-1','100.01','NaN','1.234']:
            with self.subTest(rate=rate): self.post(self.body(rate=rate),400)
        browser=APIClient(enforce_csrf_checks=True);browser.force_login(self.user)
        self.assertEqual(browser.post(self.url,self.body(),format='json').status_code,403)
        self.assertEqual(self.client.post(f'/api/me/sales/checkout/?store_id={self.other.pk}',self.body(),format='json').status_code,400)

    def test_multiple_entry_methods_sum_and_multiple_financed_rows_have_exact_fee(self):
        body=self.body(entry='140');body['payments'][1]['amount']='210'
        entry=dict(body['payments'][0]);entry['method_id']=self.methods['transfer'].pk
        balance=dict(body['payments'][1]);balance['method_id']=self.methods['boleto'].pk
        body['payments'] += [entry,balance]
        result=self.post(body)
        self.assertEqual(result.data['total'],'721.00')
        self.assertEqual(result.data['financing_amount'],'21.00')
