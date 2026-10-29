from decimal import Decimal
from uuid import uuid4
from django.contrib.auth.models import Permission
from django.test import TestCase
from sales import test_payments as fixtures
from sales.models import Sale, Quote, QuoteItem, Receivable, FinancialEntry
from sales.services import cancel_sale
from .models import Customer
from . import test_prescriptions as rx_fixtures


class CustomerHistoryTests(TestCase):
    def setUp(self):
        fixtures.PaymentCheckoutTests.setUp(self)
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label='organizations',codename__in=['view_customer','view_customer_history']))
        self.user.user_permissions.add(Permission.objects.get(content_type__app_label='sales',codename='view_receivable'))
    data=fixtures.PaymentCheckoutTests.data

    def url_history(self,section='summary',customer=None,store=None,**query):
        customer=customer or self.customer;store=store or self.store
        suffix=''.join(f'&{key}={value}' for key,value in query.items())
        return f'/api/me/customers/{customer.pk}/history/?store_id={store.pk}&section={section}{suffix}'

    def get(self,section='summary',expected=200,**options):
        response=self.client.get(self.url_history(section,**options))
        self.assertEqual(response.status_code,expected,getattr(response,'data',None))
        return response.data

    def checkout(self,**overrides):
        response=self.client.post(self.url,self.data(**overrides),format='json')
        self.assertEqual(response.status_code,200,response.data)
        return Sale.objects.get(pk=response.data['id'])

    def grant(self,app,code):
        self.user.user_permissions.add(Permission.objects.get(content_type__app_label=app,codename=code))
        for key in ('_perm_cache','_user_perm_cache','_group_perm_cache'):
            if hasattr(self.user,key):delattr(self.user,key)

    def test_empty_history_customer_identity_and_read_only(self):
        self.grant("sales","view_quote")
        result=self.get();self.assertEqual(result['customer']['id'],self.customer.pk)
        self.assertEqual(result['summary']['completed_sales'],0)
        self.assertEqual(result['summary']['customer_pending'],'0.00')
        for section in ['sales','quotes','installments']:
            self.assertEqual(self.get(section)['results'],[])
        self.assertEqual(self.client.post(self.url_history(),{},format='json').status_code,405)
        self.assertEqual(self.client.delete(self.url_history()).status_code,405)

    def test_summary_separates_customer_debt_from_card_operator(self):
        body=self.data(kind='store_credit',amount='420',count=2,confirmed=False)
        body['payments'].insert(0,self.data(amount='280')['payments'][0])
        response=self.client.post(self.url,body,format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.checkout(kind='credit',count=2,confirmed=False)
        self.checkout(kind='pix',confirmed=True)
        result=self.get()['summary']
        self.assertEqual(result['completed_sales'],3)
        self.assertEqual(result['customer_pending'],'420.00')
        self.assertEqual(result['operator_pending'],'700.00')
        self.assertEqual(self.get('installments')['count'],6)
        self.assertEqual({r['debtor'] for r in self.get('installments')['results']},{'customer','operator'})

    def test_partial_receipt_is_counted_once(self):
        sale=self.checkout(kind='store_credit',confirmed=False)
        installment=Receivable.objects.get(payment__sale=sale)
        FinancialEntry.objects.create(receivable=installment,account=self.account,method=self.methods['pix'],amount=Decimal('123.45'),created_by=self.user,reason='Parcial',request_id=uuid4())
        FinancialEntry.objects.create(receivable=installment,account=self.account,method=self.methods['pix'],amount=Decimal('10.00'),created_by=self.user,reason='Parcial 2',request_id=uuid4())
        result=self.get()['summary'];self.assertEqual(result['customer_pending'],'566.55')
        row=self.get('installments')['results'][0]
        self.assertEqual(row['remaining'],'566.55');self.assertEqual(row['status'],'partial')
        detail=self.get('installments',record_id=installment.pk)
        self.assertEqual(len([f for f in detail['fields'] if f['label'].startswith('Recebimento')]),2)

    def test_cancelled_sales_remain_visible_without_pending_debt(self):
        sale=self.checkout(kind='store_credit',confirmed=False)
        cancel_sale(user=self.admin,sale_id=sale.pk,reason='Desistência')
        summary=self.get()['summary'];self.assertEqual(summary['customer_pending'],'0.00');self.assertEqual(summary['completed_sales'],0)
        self.assertEqual(self.get('sales')['results'][0]['status'],'cancelled')
        installment=self.get('installments')['results'][0]
        self.assertEqual(installment['remaining'],'0.00');self.assertEqual(installment['status'],'cancelled')

    def test_draft_sale_does_not_count_as_completed_and_details_preserve_item_prices(self):
        sale=self.checkout(action='draft')
        summary=self.get()['summary'];self.assertEqual(summary['draft_sales'],1);self.assertEqual(summary['completed_sales'],0)
        self.product.name='Nome atual';self.product.sale_price='900';self.product.save()
        detail=self.get('sales',record_id=sale.pk)
        self.assertEqual(detail['items'][0]['name'],'Óculos');self.assertEqual(detail['items'][0]['total'],'700.00')

    def test_other_customer_and_other_unit_do_not_leak_records(self):
        sale=self.checkout();other_customer=Customer.objects.create(store=self.store,name='Outro cliente')
        self.assertEqual(self.get('sales',customer=other_customer)['count'],0)
        self.get('sales',customer=other_customer,record_id=sale.pk,expected=404)
        self.get('summary',store=self.other,expected=400)
        from accounts.models import StoreMembership
        StoreMembership.objects.create(user=self.user,store=self.other,role=StoreMembership.Role.SELLER)
        self.get('summary',store=self.other,expected=404)
        foreign=Customer.objects.create(store=self.other,name='Cliente filial')
        self.get('summary',customer=foreign,expected=404)

    def test_prescriptions_require_permission_even_counts_and_detail(self):
        result=self.get();self.assertIsNone(result['summary']['prescriptions']);self.assertFalse(result['permissions']['prescriptions'])
        self.get('prescriptions',expected=403)
        rx_fixtures.PrescriptionAPITests.grant(self)
        response=self.client.post(f'/api/me/prescriptions/?store_id={self.store.pk}',rx_fixtures.PrescriptionAPITests.data(self),format='json')
        self.assertEqual(response.status_code,200,response.data)
        rx_id=response.data['id']
        result=self.get('prescriptions');self.assertIsNone(result['results'][0]['clinical'])
        detail=self.get('prescriptions',record_id=rx_id)
        self.assertEqual(detail['clinical']['od_sphere'],'-1.25')
        self.assertEqual(self.get()['summary']['prescriptions'],1)
        self.user.user_permissions.clear()
        for key in ('_perm_cache','_user_perm_cache','_group_perm_cache'):
            if hasattr(self.user,key):delattr(self.user,key)
        self.get('prescriptions',record_id=rx_id,expected=403)

    def test_service_order_permission_does_not_grant_clinical_access(self):
        sale=self.checkout()
        self.get('orders',expected=403);self.assertIsNone(self.get()['summary']['orders'])
        self.grant('sales','view_serviceorder');self.grant('sales','add_serviceorder')
        response=self.client.post(f'/api/me/service-orders/?store_id={self.store.pk}',{'request_id':str(uuid4()),'action':'create','sale_id':sale.pk,'promised_on':'2026-12-01','laboratory':'Lab'},format='json')
        self.assertEqual(response.status_code,200,response.data)
        detail=self.get('orders',record_id=response.data['id'])
        self.assertIsNone(detail['clinical']);self.assertEqual(detail['sale_id'],sale.pk)
        self.assertEqual(self.get()['summary']['orders'],1)

    def test_quotes_include_current_snapshot_and_link(self):
        self.grant("sales","view_quote")
        quote=Quote.objects.create(store=self.store,customer=self.customer,created_by=self.user,valid_until='2026-12-01')
        QuoteItem.objects.create(quote=quote,product=self.product,quantity='1',unit_price='700')
        result=self.get('quotes',record_id=quote.pk)
        self.assertEqual(result['amount'],'700.00');self.assertEqual(result['items'][0]['name'],self.product.name)
        self.assertEqual(self.get()['summary']['quotes'],1)

    def test_inactive_customer_history_remains_readable(self):
        self.checkout();self.customer.is_active=False;self.customer.save()
        self.assertFalse(self.get()['customer']['is_active']);self.assertEqual(self.get('sales')['count'],1)

    def test_pagination_has_stable_order_and_detail_scope(self):
        for _ in range(27):Sale.objects.create(store=self.store,customer=self.customer,created_by=self.user)
        first=self.get('sales');second=self.get('sales',page=2)
        self.assertEqual(first['count'],27);self.assertEqual(len(first['results']),25);self.assertEqual(len(second['results']),2)
        self.assertFalse(set(r['id'] for r in first['results'])&set(r['id'] for r in second['results']))
        self.get('sales',page=99,expected=404)
        for value in ['bad','-2']:
            self.get('sales',record_id=value,expected=400)
        self.get('bad',expected=400)

    def test_authentication_revocation_and_private_cache(self):
        response=self.client.get(self.url_history());self.assertEqual(response['Cache-Control'],'no-store, private')
        from accounts.models import StoreMembership
        StoreMembership.objects.filter(user=self.user).update(is_active=False)
        self.get(expected=400)
        self.client.force_authenticate(None);self.get(expected=403)

    def test_overdue_summary_ignores_operator_and_cancelled_amounts(self):
        self.checkout(kind='store_credit',confirmed=False)
        self.checkout(kind='credit',confirmed=False)
        Receivable.objects.all().update(due_date='2026-01-01')
        result=self.get()['summary']
        self.assertEqual(result['customer_overdue'],'700.00')
        self.assertEqual(result['operator_pending'],'700.00')
        self.assertEqual(len([r for r in self.get('installments')['results'] if r['overdue']]),2)

    def test_missing_store_and_inactive_store_deny_access(self):
        response=self.client.get(f'/api/me/customers/{self.customer.pk}/history/')
        self.assertEqual(response.status_code,400)
        self.store.is_active=False;self.store.save()
        self.get(expected=400)
