import csv
import io
from datetime import date, datetime, timedelta, timezone as utc
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth.models import Permission
from django.test import TestCase, SimpleTestCase
from rest_framework.test import APIClient
from . import test_payments as fixtures
from .models import Receivable, Sale, FinancialEntry
from .services import cancel_sale
from .receivable_report import classify
from organizations.models import StockMovement

NOW = datetime(2026,10,28,15,tzinfo=utc.utc)
TODAY = date(2026,10,28)


class ReceivableRiskTests(SimpleTestCase):
    def test_thresholds_and_paid_override(self):
        expected={8:('within',0,''),7:('soon',0,''),0:('soon',0,''),-1:('overdue',1,'1_30'),-30:('overdue',30,'1_30'),
            -31:('overdue',31,'31_60'),-60:('overdue',60,'31_60'),-61:('overdue',61,'61_90'),-90:('overdue',90,'61_90'),-91:('critical',91,'over_90')}
        for delta,result in expected.items():
            with self.subTest(delta=delta):
                self.assertEqual(classify(TODAY+timedelta(days=delta),Decimal('1'),TODAY,7),result)
                self.assertEqual(classify(TODAY+timedelta(days=delta),Decimal('0'),TODAY,7),('paid',0,''))


class ReceivableManagementReportTests(TestCase):
    def setUp(self):
        fixtures.PaymentCheckoutTests.setUp(self)
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label='sales',codename__in=['view_reports','export_reports','view_receivable']))

    def create_row(self, days=0, *, amount='100', kind='store_credit', confirmed=False, name=None):
        if name:
            self.customer.name=name;self.customer.save()
        body=fixtures.PaymentCheckoutTests.data(self,kind=kind,amount=amount,confirmed=confirmed)
        body['items'][0]['unit_price']=amount
        body['payments'][0]['first_due_date']=(TODAY+timedelta(days=days)).isoformat()
        with patch('django.utils.timezone.now',return_value=NOW):
            response=self.client.post(self.url,body,format='json')
        self.assertEqual(response.status_code,200,response.data)
        return Receivable.objects.get(payment__sale_id=response.data['id'])

    def report(self, expected=200, **extra):
        params={'store_id':self.store.pk,'report':'receivables','all_dates':'true','status':'all',**extra}
        with patch('django.utils.timezone.now',return_value=NOW):
            response=self.client.get('/api/me/reports/',params)
        self.assertEqual(response.status_code,expected,getattr(response,'data',response.content[:500]))
        return response

    def receipt(self,row,amount,**extra):
        return FinancialEntry.objects.create(receivable=row,account=self.account,method=self.methods['pix'],amount=Decimal(amount),created_by=self.user,reason='Conferência',**extra)

    def metrics(self,response):return {m['key']:m['value'] for m in response.data['summary']}

    def test_boundaries_colors_and_aging_sum_all_pages(self):
        for delta in [8,7,0,-1,-30,-31,-60,-61,-90,-91]:self.create_row(delta)
        response=self.report(page_size=1)
        self.assertEqual(response.data['count'],10);self.assertEqual(len(response.data['results']),1)
        metrics=self.metrics(response)
        self.assertEqual(metrics['remaining'],'1000.00');self.assertEqual(metrics['overdue'],'700.00')
        self.assertEqual(metrics['within'],'100.00');self.assertEqual(metrics['soon'],'200.00');self.assertEqual(metrics['critical'],'100.00')
        self.assertEqual([b['amount'] for b in response.data['aging']],['200.00','200.00','200.00','100.00'])
        self.assertEqual(response.data['results'][0]['tone'],'black')
        self.assertEqual(response.data['results'][0]['days_overdue'],'91')
        second=self.report(page_size=1,page=2)
        self.assertEqual(second.data['results'][0]['tone'],'red')
        self.assertEqual(response.data['summary'],second.data['summary'])
        self.assertEqual(response.data['aging'],second.data['aging'])

    def test_paid_old_installment_is_gray_and_outside_aging(self):
        row=self.create_row(-150);self.receipt(row,'100')
        response=self.report();item=response.data['results'][0]
        self.assertEqual((item['tone'],item['risk_label'],item['days_overdue']),('gray','Quitada','0'))
        self.assertTrue(all(b['count']==0 for b in response.data['aging']))
        self.assertEqual(self.metrics(response)['remaining'],'0.00')
        self.assertEqual(self.report(risk='critical').data['count'],0)

    def test_partial_receipts_and_reversal_do_not_multiply_balances(self):
        row=self.create_row(-91);first=self.receipt(row,'25');self.receipt(row,'10')
        response=self.report(status='partial');metrics=self.metrics(response)
        self.assertEqual((metrics['original'],metrics['paid'],metrics['remaining']),('100.00','35.00','65.00'))
        self.assertEqual(response.data['results'][0]['status'],'Paga parcialmente')
        self.receipt(row,'-25',reversal_of=first)
        response=self.report();self.assertEqual(self.metrics(response)['remaining'],'90.00')
        self.assertEqual(response.data['aging'][-1]['amount'],'90.00')

    def test_custom_warning_window_and_today_not_overdue(self):
        self.create_row(10);self.create_row(0)
        self.assertEqual(self.report(risk='soon').data['count'],1)
        self.assertEqual(self.report(risk='soon',warning_days=10).data['count'],2)
        self.assertEqual(self.report(status='overdue').data['count'],0)

    def test_filters_customer_sale_method_risk_and_age(self):
        row=self.create_row(-40,kind='boleto',name='Maria da Silva')
        self.create_row(20,kind='credit',name='João Almeida')
        result=self.report(customer='Maria',sale_id=row.payment.sale_id,method='boleto',risk='overdue',aging='31_60')
        self.assertEqual(result.data['count'],1);self.assertEqual(result.data['results'][0]['id'],f'#{row.pk}')
        self.assertEqual(self.report(customer='João',method='boleto').data['count'],0)
        self.assertEqual(self.report(debtor='operator').data['count'],1)
        self.assertEqual(self.report(debtor='customer').data['count'],1)

    def test_date_filter_and_all_dates_include_debts_older_than_year(self):
        self.create_row(-500);self.create_row(0)
        result=self.report(all_dates='false',start='2026-10-01',end='2026-10-31')
        self.assertEqual(result.data['count'],1)
        self.assertEqual(self.report().data['count'],2)
        self.assertEqual(self.report(all_dates='true',start='2020-01-01',end='2026-10-31').data['count'],2)

    def test_cancelled_and_draft_sales_excluded(self):
        row=self.create_row(-20)
        cancel_sale(user=self.admin,sale_id=row.payment.sale_id,reason='Cancelamento teste')
        body=fixtures.PaymentCheckoutTests.data(self,action='draft')
        self.assertEqual(self.client.post(self.url,body,format='json').status_code,200)
        self.assertEqual(self.report().data['count'],0)

    def test_new_financing_total_is_already_in_original_and_pending(self):
        body=fixtures.PaymentCheckoutTests.data(self,amount='280')
        body['financing_rate']='5'
        body['payments'].append(fixtures.PaymentCheckoutTests.data(self,kind='store_credit',amount='420',count=2,confirmed=False)['payments'][0])
        response=self.client.post(self.url,body,format='json');self.assertEqual(response.status_code,200,response.data)
        metrics=self.metrics(self.report())
        self.assertEqual((metrics['original'],metrics['paid'],metrics['remaining']),('721.00','280.00','441.00'))

    def test_unit_and_permission_checks_apply_to_screen_csv_and_print(self):
        self.create_row(-91)
        for export in [None,'csv','print']:
            params={'export':export} if export else {}
            self.report(expected=400,store_id=self.other.pk,**params)
        self.user.user_permissions.remove(Permission.objects.get(content_type__app_label='sales',codename='export_reports'))
        self.report();self.report(expected=403,export='csv');self.report(expected=403,export='print')
        self.user.user_permissions.remove(Permission.objects.get(content_type__app_label='sales',codename='view_receivable'))
        self.report(expected=403)

    def test_no_source_access_is_not_restored_by_export_right(self):
        self.user.user_permissions.remove(Permission.objects.get(content_type__app_label='sales',codename='view_receivable'))
        self.report(expected=403,export='print');self.report(expected=403,export='csv')
        self.client.force_authenticate(None);self.report(expected=403)

    def test_csv_contains_all_filtered_rows_labels_days_and_formula_protection(self):
        row=self.create_row(-91,name='Cliente especial')
        Receivable.objects.filter(pk=row.pk).update(customer_name='=SUM(1;1)')
        self.create_row(0)
        response=self.report(page_size=1,export='csv')
        rows=list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig')),delimiter=';'))
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['Prazo'],'Acima de 90 dias')
        self.assertEqual(rows[0]['Dias em atraso'],'91')
        self.assertEqual(rows[0]['Cliente registrado'],"'=SUM(1;1)")
        self.assertIn('todos-vencimentos',response['Content-Disposition'])

    def test_print_contains_all_pages_filters_summary_and_escaped_customer(self):
        self.create_row(-91,name='<script>alert(1)</script>')
        self.create_row(0,name='Maria')
        result=self.report(page_size=1,export='print',warning_days=10)
        html=result.content.decode()
        self.assertIn('text/html',result['Content-Type'])
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;',html);self.assertNotIn('<script>alert(1)</script>',html)
        self.assertIn('Maria',html);self.assertIn('2 parcela(s)',html);self.assertIn('10 dias',html)
        self.assertIn('Todos os vencimentos',html)
        self.assertIn('28/10/2026 12:00 (São Paulo)',html)
        self.assertEqual(result['Cache-Control'],'no-store, private')
        self.assertIn("default-src 'none'",result['Content-Security-Policy'])

    def test_print_limit_checks_count_and_iterator_without_partial_document(self):
        self.create_row(-1);self.create_row(-2)
        with patch('sales.report_views.MAX_PRINT_ROWS',1):self.report(expected=400,export='print')
        with patch('sales.report_views.MAX_PRINT_ROWS',1),patch('django.db.models.query.QuerySet.count',return_value=1):
            self.report(expected=400,export='print')

    def test_bad_filters_are_rejected(self):
        for params in [{'warning_days':0},{'warning_days':91},{'warning_days':'a'},{'all_dates':'nonsense'},
                       {'customer':'x'*121},{'method':'unknown'},{'risk':'unknown'},{'aging':'unknown'},
                       {'sale_id':0},{'sale_id':2**63},{'all_dates':'false','start':'2020-01-01','end':'2026-10-01'}]:
            with self.subTest(params=params):self.report(expected=400,**params)
        self.report(expected=400,report='sales',export='print')

    def test_sao_paulo_date_boundary(self):
        self.create_row(0)
        with patch('django.utils.timezone.now',return_value=datetime(2026,10,29,2,59,tzinfo=utc.utc)):
            response=self.client.get('/api/me/reports/',{'store_id':self.store.pk,'report':'receivables','all_dates':'true'})
        self.assertEqual(response.data['today'],'2026-10-28');self.assertEqual(response.data['results'][0]['risk'],'soon')
        with patch('django.utils.timezone.now',return_value=datetime(2026,10,29,3,0,tzinfo=utc.utc)):
            response=self.client.get('/api/me/reports/',{'store_id':self.store.pk,'report':'receivables','all_dates':'true'})
        self.assertEqual(response.data['results'][0]['days_overdue'],'1')

    def test_no_write_or_stock_money_side_effect(self):
        self.create_row(-100)
        models=[Sale,Receivable,FinancialEntry,StockMovement]
        before=[model.objects.count() for model in models]
        self.report();self.report(export='csv');self.report(export='print')
        self.assertEqual([model.objects.count() for model in models],before)
        self.assertEqual(self.client.post('/api/me/reports/',{},format='json').status_code,405)
