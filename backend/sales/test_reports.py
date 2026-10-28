import csv
import io
from datetime import datetime, date, timedelta, timezone as utc
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth.models import Permission
from django.test import TestCase
from rest_framework.test import APIClient
from accounts.models import StoreMembership
from organizations.models import Supplier, StockMovement
from purchases import tests as purchase_tests
from purchases.models import PayablePlan, PayablePayment
from purchases.payable_services import generate_plan, pay_installment, reverse_payment
from . import test_payments as sale_fixtures
from .models import CashPosting, FinancialAccount, FinancialEntry, Receivable, Sale
from .cash_services import open_cash, move_cash

NOW=datetime(2026,10,19,15,tzinfo=utc.utc)


class ReportsTests(TestCase):
    setUp=sale_fixtures.PaymentCheckoutTests.setUp
    data=sale_fixtures.PaymentCheckoutTests.data
    path=purchase_tests.PurchaseTests.path
    write=purchase_tests.PurchaseTests.write

    def grant(self,user=None,app='sales',codes=None):
        user=user or self.user
        codes=codes or ['view_sale','view_financialentry','view_receivable','view_reports','export_reports']
        user.user_permissions.add(*Permission.objects.filter(content_type__app_label=app,codename__in=codes))
        for key in ('_perm_cache','_user_perm_cache','_group_perm_cache'):
            if hasattr(user,key):delattr(user,key)

    def grant_all(self,user=None):
        self.grant(user)
        self.grant(user,app='purchases',codes=['view_payableplan','add_payableplan','pay_payable','reverse_payable','view_purchase','add_purchase','change_purchase','receive_purchase'])

    def report(self,kind='sales',expected=200,**params):
        values={'store_id':self.store.pk,'report':kind,'start':'2026-10-01','end':'2026-10-31',**params}
        with patch('django.utils.timezone.now',return_value=NOW):response=self.client.get('/api/me/reports/',values)
        self.assertEqual(response.status_code,expected,getattr(response,'data',response.content[:500]))
        return response

    def summary(self,response):return {m['key']:m['value'] for m in response.data['summary']}

    def sale(self,at=NOW,**options):
        body=self.data(**options);body['payments'][0]['first_due_date']='2026-10-01'
        with patch('django.utils.timezone.now',return_value=at):response=self.client.post(self.url,body,format='json')
        self.assertEqual(response.status_code,200,response.data)
        return response.data

    def purchase_plan(self,amount='100.01',name='Laboratório de testes'):
        self.grant_all()
        self.supplier=Supplier(store=self.store,name=name,created_by=self.user,updated_by=self.user);self.supplier.save(_service=True)
        record=self.write(purchase_tests.PurchaseTests.data(self,reference=str(uuid4()),items=[{'product_id':self.product.pk,'quantity':'1','unit_cost':amount}]))
        purchase_tests.PurchaseTests.action(self,record)
        with patch('django.utils.timezone.now',return_value=NOW):
            return generate_plan(user=self.user,store=self.store,values={'request_id':uuid4(),'purchase_id':record['id'],'installment_count':2,'first_due_date':date(2026,10,1),'interval_unit':'days','interval_count':1})

    def payout(self,plan,amount='10',at=NOW,**extra):
        values={'request_id':uuid4(),'account_id':self.account.pk,'method_id':self.methods['pix'].pk,'amount':Decimal(amount),'paid_on':date(2026,10,18),'reason':'Comprovante fornecedor',**extra}
        with patch('django.utils.timezone.now',return_value=at):return pay_installment(user=self.user,store=self.store,installment_id=plan.installments.first().pk,values=values)

    def test_permissions_options_and_staff_do_not_bypass(self):
        # A fixture de checkout agora concede direitos explícitos de vendas.
        # Este caso começa sem consulta para continuar testando a negação do relatório.
        permission = Permission.objects.filter(content_type__app_label='sales', codename__in=['view_sale','view_receivable'])
        for user in (self.user, self.admin):
            user.user_permissions.remove(*permission)
            for cache in ('_perm_cache', '_user_perm_cache', '_group_perm_cache'):
                if hasattr(user, cache): delattr(user, cache)
        self.report(expected=403)
        self.client.force_authenticate(self.admin);self.report(expected=403)
        response=self.client.get('/api/me/reports/options/',{'store_id':self.store.pk})
        self.assertEqual(response.status_code,200);self.assertEqual(response.data['reports'],[]);self.assertEqual(response.data['accounts'],[])
        self.grant(self.admin,codes=['view_sale'])
        response=self.client.get('/api/me/reports/options/',{'store_id':self.store.pk})
        self.assertEqual([r['key'] for r in response.data['reports']],['sales'])
        self.report();self.report('movements',expected=403);self.report('payables',expected=403)
        self.report('sales',expected=200,export='csv')

    def test_anonymous_inactive_user_and_unlinked_unit(self):
        self.grant_all();self.client.force_authenticate(None);self.report(expected=403)
        self.client.force_authenticate(self.user);self.report(expected=400,store_id=self.other.pk)
        self.user.is_active=False;self.user.save();self.report(expected=403)

    def test_empty_reports_and_no_write_endpoints(self):
        self.grant_all()
        for kind in ['sales','movements','receivables','payables']:
            response=self.report(kind)
            self.assertEqual(response.data['count'],0);self.assertEqual(response.data['results'],[])
            self.assertTrue(all(Decimal(v)==0 for v in self.summary(response).values()))
            self.assertEqual(response['Cache-Control'],'no-store, private')
        self.assertEqual(self.client.post('/api/me/reports/?store_id='+str(self.store.pk),{},format='json').status_code,405)

    def test_invalid_dates_ids_filters_and_maximum_period(self):
        self.grant_all()
        for params in [{'start':'2026-11-01'},{'start':'2024-01-01'},{'end':'invalid'},{'end':'9999-12-31'},{'status':'other'},{'report':'unknown'},{'page':'0'},{'page_size':'101'},{'account_id':'not-a-number'},{'export':'pdf'}]:self.report(expected=400,**params)
        with patch('django.utils.timezone.now',return_value=NOW):response=self.client.get('/api/me/reports/',{'store_id':self.store.pk,'start':'2026-10-01'})
        self.assertEqual(response.status_code,400)
        self.report('movements',expected=400,account_id=self.other_account.pk)

    def test_sales_totals_do_not_multiply_for_multiple_payments_or_items(self):
        self.grant_all();body=self.data(kind='pix',amount='350');body['payments'].append({**body['payments'][0],'amount':'350'});body['items']=[{**body['items'][0],'quantity':'0.500'},{'product_id':self.product.pk,'quantity':'0.500','unit_price':'700','discount_amount':'0'}]
        # A venda não admite produto repetido: dois produtos reais mantêm o teste de joins.
        from organizations.models import Product
        second=Product.objects.create(store=self.store,internal_code='REPORT2',name='Lentes',sale_price='700',stock_quantity='10')
        body['items'][1]['product_id']=second.pk
        with patch('django.utils.timezone.now',return_value=NOW):response=self.client.post(self.url,body,format='json')
        self.assertEqual(response.status_code,200,response.data)
        result=self.report();self.assertEqual(self.summary(result),{'count':'1','total':'700.00','ticket':'700.00'})
        self.assertEqual(result.data['results'][0]['amount'],response.data['total'])

    def test_sales_exact_line_rounding_and_global_discount(self):
        self.grant_all();body=self.data(amount='0.01');body['items'][0].update(quantity='0.001',unit_price='5')
        with patch('django.utils.timezone.now',return_value=NOW):response=self.client.post(self.url,body,format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(self.summary(self.report())['total'],'0.01')
        body=self.data(amount='550');body['discount_amount']='50';body['items'][0]['discount_amount']='100'
        with patch('django.utils.timezone.now',return_value=NOW):response=self.client.post(self.url,body,format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(self.summary(self.report())['total'],'550.01')

    def test_local_day_boundaries_are_sao_paulo(self):
        self.grant_all()
        self.sale(at=datetime(2026,10,19,2,59,tzinfo=utc.utc));self.sale(at=datetime(2026,10,19,3,0,tzinfo=utc.utc))
        self.assertEqual(self.summary(self.report(start='2026-10-19',end='2026-10-19'))['count'],'1')
        self.assertEqual(self.summary(self.report('movements',start='2026-10-19',end='2026-10-19'))['incoming'],'700.00')

    def test_drafts_and_cancelled_sales_excluded_refund_stays_in_movements(self):
        self.grant_all();record=self.sale(at=NOW-timedelta(days=1));self.sale(action='draft')
        self.client.force_authenticate(self.admin)
        with patch('django.utils.timezone.now',return_value=NOW):response=self.client.post(f'/api/me/sales/{record["id"]}/cancel/?store_id={self.store.pk}',{'reason':'Devolução'},format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.report().data['count'],0)
        self.assertEqual(self.report('receivables',status='all').data['count'],0)
        sums=self.summary(self.report('movements',start='2026-10-19',end='2026-10-19'))
        self.assertEqual(sums['incoming'],'0.00');self.assertEqual(sums['outgoing'],'700.00');self.assertEqual(sums['net'],'-700.00')

    def test_partial_receipts_sum_once_and_responsibilities_are_separate(self):
        self.grant_all();self.sale(kind='store_credit',confirmed=False);self.sale(kind='credit',confirmed=False)
        installment=Receivable.objects.get(debtor='customer')
        self.client.force_authenticate(self.admin)
        for amount in ['25','50']:
            response=self.client.post(f'/api/me/receivables/{installment.pk}/receive/?store_id={self.store.pk}',{'request_id':str(uuid4()),'amount':amount,'account_id':self.account.pk,'method_id':self.methods['pix'].pk},format='json')
            self.assertEqual(response.status_code,200,response.data)
        self.client.force_authenticate(self.user)
        sums=self.summary(self.report('receivables',debtor='customer'))
        self.assertEqual(sums['original'],'700.00');self.assertEqual(sums['paid'],'75.00');self.assertEqual(sums['remaining'],'625.00')
        sums=self.summary(self.report('receivables',debtor='operator'));self.assertEqual(sums['remaining'],'700.00')

    def test_payable_due_date_filter_uses_current_balance_after_later_payment(self):
        plan=self.purchase_plan();self.payout(plan)
        result=self.report('payables',start='2026-10-01',end='2026-10-01')
        sums=self.summary(result)
        self.assertEqual(sums['count'],'1');self.assertEqual(sums['original'],'50.01');self.assertEqual(sums['paid'],'10.00');self.assertEqual(sums['remaining'],'40.01')
        self.assertIn('saldo atual',result.data['basis'])

    def test_payables_paid_pending_overdue_and_reversal(self):
        plan=self.purchase_plan();payment=self.payout(plan,'50.01')
        self.assertEqual(self.report('payables',status='paid').data['count'],1)
        self.assertEqual(self.report('payables',status='pending').data['count'],1)
        self.assertEqual(self.summary(self.report('payables',status='overdue'))['remaining'],'50.00')
        with patch('django.utils.timezone.now',return_value=NOW):reverse_payment(user=self.user,store=self.store,payment_id=payment.pk,values={'request_id':uuid4(),'reason':'Correção'})
        self.assertEqual(self.report('payables',status='paid').data['count'],0)
        self.assertEqual(self.summary(self.report('payables',status='all'))['remaining'],'100.01')

    def test_due_today_is_not_overdue(self):
        self.grant_all();self.sale(kind='store_credit',confirmed=False)
        Receivable.objects.update(due_date=date(2026,10,19))
        self.assertEqual(self.report('receivables',status='overdue').data['count'],0)
        self.assertEqual(self.report('receivables',status='pending').data['count'],1)

    def test_movement_direction_signs_reversal_and_account_filter(self):
        plan=self.purchase_plan();self.sale();payment=self.payout(plan)
        with patch('django.utils.timezone.now',return_value=NOW):reverse_payment(user=self.user,store=self.store,payment_id=payment.pk,values={'request_id':uuid4(),'reason':'Correção'})
        response=self.report('movements');sums=self.summary(response)
        self.assertEqual(sums,{'count':'3','incoming':'710.00','outgoing':'10.00','net':'700.00'})
        self.assertEqual(self.report('movements',direction='in').data['count'],2)
        self.assertEqual(self.report('movements',direction='out').data['count'],1)
        self.assertEqual(self.report('movements',account_id=self.account.pk).data['count'],3)
        empty=FinancialAccount.objects.create(store=self.store,code='empty',name='Outra conta')
        self.assertEqual(self.report('movements',account_id=empty.pk).data['count'],0)

    def test_backdated_payout_uses_recorded_day_and_shows_payment_date(self):
        plan=self.purchase_plan();self.payout(plan)
        self.assertEqual(self.report('movements',start='2026-10-18',end='2026-10-18').data['count'],0)
        row=self.report('movements',start='2026-10-19',end='2026-10-19').data['results'][0]
        self.assertEqual(row['paid_on'],'2026-10-18');self.assertEqual(row['amount'],'-10.00')

    def test_cash_is_not_counted_twice_and_manual_postings_are_excluded(self):
        plan=self.purchase_plan();cash=FinancialAccount.objects.create(store=self.store,code='cash',name='Caixa')
        session=open_cash(user=self.user,store=self.store,account_id=cash.pk,amount=Decimal('100'),note='',request_id=uuid4())
        move_cash(user=self.user,store=self.store,session_id=session.pk,kind='supply',amount=Decimal('20'),reason='Troco',request_id=uuid4())
        self.payout(plan,account_id=cash.pk,method_id=self.methods['cash'].pk,paid_on=date(2026,10,19))
        result=self.report('movements');self.assertEqual(result.data['count'],1);self.assertEqual(self.summary(result)['outgoing'],'10.00');self.assertEqual(CashPosting.objects.count(),2)

    def test_unit_scoping_and_inactive_accounts_remain_available_for_history(self):
        plan=self.purchase_plan();self.payout(plan)
        StoreMembership.objects.create(user=self.user,store=self.other,role=StoreMembership.Role.SELLER)
        for kind in ['sales','movements','receivables','payables']:self.assertEqual(self.report(kind,store_id=self.other.pk,status='all').data['count'],0)
        self.account.is_active=False;self.account.save()
        options=self.client.get('/api/me/reports/options/',{'store_id':self.store.pk}).data
        self.assertIn(self.account.pk,[a['id'] for a in options['accounts']]);self.assertNotIn(self.other_account.pk,[a['id'] for a in options['accounts']])
        self.assertEqual(self.report('movements',account_id=self.account.pk).data['count'],1)

    def test_pagination_and_csv_export_all_filtered_rows(self):
        self.grant_all()
        created_ids = []
        for _ in range(3):
            # Rascunhos consomem IDs sem entrar no relatório. A sequência
            # também pode avançar entre testes executados no PostgreSQL.
            self.sale(action='draft')
            created_ids.append(self.sale()['id'])
        expected_ids = [f'#{pk}' for pk in reversed(created_ids)]

        page = self.report(page_size=1)
        self.assertEqual(page.data['count'], 3)
        self.assertEqual(len(page.data['results']), 1)
        self.assertIsNotNone(page.data['next'])
        self.assertEqual(page.data['results'][0]['id'], expected_ids[0])
        self.assertEqual(self.summary(page)['total'], '2100.00')

        second = self.report(page_size=1, page=2)
        third = self.report(page_size=1, page=3)
        actual_ids = [result.data['results'][0]['id'] for result in (page, second, third)]
        self.assertEqual(actual_ids, expected_ids)
        self.assertEqual(len(set(actual_ids)), 3)
        self.assertIsNone(third.data['next'])

        response = self.report(page_size=1, export='csv')
        self.assertTrue(response.content.startswith(b'\xef\xbb\xbf'))
        self.assertIn('attachment', response['Content-Disposition'])
        rows = list(csv.reader(io.StringIO(response.content.decode('utf-8-sig')), delimiter=';'))
        self.assertEqual(len(rows), 4)
        self.assertEqual([row[1] for row in rows[1:]], expected_ids)
        self.assertTrue(all(row[-1] == '700,00' for row in rows[1:]))

    def test_union_movement_pagination_and_export(self):
        plan=self.purchase_plan();self.sale();self.payout(plan)
        response=self.report('movements',page_size=1)
        self.assertEqual(response.data['count'],2);self.assertEqual(len(response.data['results']),1)
        other=self.report('movements',page_size=1,page=2)
        self.assertNotEqual(response.data['results'][0]['id'],other.data['results'][0]['id'])
        exported=self.report('movements',page_size=1,export='csv')
        rows=list(csv.reader(io.StringIO(exported.content.decode('utf-8-sig')),delimiter=';'));self.assertEqual(len(rows),3)

    def test_csv_escapes_formula_text_and_keeps_signed_amount_numeric(self):
        name=' =HYPERLINK("teste");linha\nÓtica'
        plan=self.purchase_plan(name=name);self.payout(plan)
        response=self.report('movements',export='csv')
        rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig')),delimiter=';'))
        self.assertEqual(rows[1][7],"'"+name.strip());self.assertEqual(rows[1][-2],'-10,00')

    def test_csv_limit_rejects_instead_of_silent_truncation(self):
        self.grant_all();self.sale();self.sale()
        with patch('sales.report_views.MAX_EXPORT_ROWS',1):response=self.report(expected=400,export='csv')
        self.assertNotIn('Content-Disposition',response)

    def test_csv_still_rejects_limit_if_more_rows_appear_after_count(self):
        self.grant_all();self.sale();self.sale()
        with patch('sales.report_views.MAX_EXPORT_ROWS',1), patch('django.db.models.query.QuerySet.count',return_value=1):
            response=self.report(expected=400,export='csv')
        self.assertNotIn('Content-Disposition',response)

    def test_report_read_has_no_stock_or_financial_side_effects(self):
        plan=self.purchase_plan();self.sale();self.payout(plan)
        models=[StockMovement,FinancialEntry,PayablePayment,CashPosting,Receivable,PayablePlan,Sale]
        before=[model.objects.count() for model in models]
        for kind in ['sales','movements','receivables','payables']:
            self.report(kind,status='all');self.report(kind,status='all',export='csv')
        self.assertEqual([model.objects.count() for model in models],before)
