import uuid
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission, Group
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from accounts.models import StoreMembership
from organizations.models import Company, Store, Customer, Product, StockMovement
from .models import Quote, QuoteItem, QuoteEvent, QuoteOperation, Sale, FinancialEntry, Receivable
from .quote_services import operate_quote


class QuotePermissionTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user(username='quote-rights',password='test-only-password')
        self.company=Company.objects.create(name='Empresa de propostas')
        self.store=Store.objects.create(company=self.company,code='QP1',name='Matriz')
        self.other=Store.objects.create(company=self.company,code='QP2',name='Filial')
        self.link=StoreMembership.objects.create(user=self.user,store=self.store,role='manager')
        self.customer=Customer.objects.create(store=self.store,name='Cliente proposta')
        self.product=Product.objects.create(store=self.store,internal_code='QP1',name='Armação',cost_price=40,sale_price=100,stock_quantity=0)
        self.other_product=Product.objects.create(store=self.other,internal_code='QP2',name='Produto filial')
        self.quote=Quote.objects.create(store=self.store,customer=self.customer,created_by=self.user,valid_until=timezone.localdate()+timedelta(days=30))
        QuoteItem.objects.create(quote=self.quote,product=self.product,quantity=1,unit_price=100)
        self.client=APIClient();self.client.force_authenticate(self.user)

    def grant(self,*actions,sale_add=False):
        self.user.user_permissions.set(Permission.objects.filter(content_type__app_label='sales',content_type__model='quote',codename__in=[a+'_quote' for a in actions]))
        if sale_add:self.user.user_permissions.add(Permission.objects.get(content_type__app_label='sales',codename='add_sale'))

    def url(self,path='',store=None):return f'/api/me/quotes/{path}?store_id={(store or self.store).pk}'
    def write(self,body=None,quote=None):
        if quote is not None:return self.client.put(self.url(f'{quote.pk}/'),body or self.payload(),format='json')
        return self.client.post(self.url(),body or self.payload(),format='json')
    def payload(self,**extra):return {'request_id':str(uuid.uuid4()),'customer_id':self.customer.pk,'valid_until':str(timezone.localdate()+timedelta(days=30)),'notes':'Proposta de teste','discount_amount':'0','items':[{'product_id':self.product.pk,'quantity':'1','unit_price':'100','discount_amount':'0'}],**extra}
    def action(self,name,quote=None,**extra):
        quote=quote or self.quote;quote.refresh_from_db()
        return self.client.post(self.url(f'{quote.pk}/{name}/'),{'request_id':str(uuid.uuid4()),'expected_version':quote.version,**extra},format='json')
    def state(self,value):
        self.quote.status=value;self.quote.save(_allow_transition=True)
    def no_effects(self):
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,0)
        self.assertFalse(StockMovement.objects.exists());self.assertFalse(FinancialEntry.objects.exists());self.assertFalse(Receivable.objects.exists())

    def test_staff_manager_and_sale_rights_do_not_grant_quote_rights(self):
        self.user.is_staff=True;self.user.save(update_fields=['is_staff'])
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label='sales',content_type__model='sale'))
        for suffix in ['',f'{self.quote.pk}/',f'{self.quote.pk}/print/','options/']:
            self.assertEqual(self.client.get(self.url(suffix)).status_code,403)
        self.assertEqual(self.write().status_code,403)
        for name in ['send','accept','reject','convert']:self.assertEqual(self.action(name,reason='Teste').status_code,403)
        self.no_effects();self.assertFalse(Sale.objects.exists());self.assertFalse(QuoteEvent.objects.exists())

    def test_view_only_has_no_write_transition_or_print(self):
        self.grant('view')
        r=self.client.get(self.url(f'{self.quote.pk}/'));self.assertEqual(r.status_code,200)
        for key in ['change','send','accept','reject','convert','print']:self.assertFalse(r.data['actions'][key])
        self.assertEqual(self.write().status_code,403)
        self.assertEqual(self.write(self.payload(expected_version=1),self.quote).status_code,403)
        for name in ['send','accept','reject','convert']:self.assertEqual(self.action(name,reason='Teste').status_code,403)
        self.assertEqual(self.client.get(self.url(f'{self.quote.pk}/print/')).status_code,403)

    def test_add_without_view_can_create_and_replay_without_listing(self):
        self.grant('add');body=self.payload()
        first=self.write(body);self.assertEqual(first.status_code,200,first.data)
        self.assertEqual(self.write(body).data['id'],first.data['id'])
        self.assertEqual(Quote.objects.count(),2);self.assertFalse(first.data['actions']['change'])
        self.assertEqual(self.client.get(self.url()).status_code,403)
        self.assertEqual(self.client.get(self.url(f'{first.data["id"]}/')).status_code,403)
        self.grant();self.assertEqual(self.write(body).status_code,403)
        self.assertEqual(Quote.objects.count(),2);self.no_effects()

    def test_change_does_not_grant_create_send_or_accept(self):
        self.grant('change')
        self.assertEqual(self.write(self.payload(expected_version=1),self.quote).status_code,200)
        self.assertEqual(self.write().status_code,403)
        self.assertEqual(self.action('send').status_code,403);self.assertEqual(self.action('accept').status_code,403)
        self.no_effects()

    def test_prepare_and_accept_are_independent_of_editing(self):
        self.grant('view','send')
        r=self.action('send');self.assertEqual(r.status_code,200,r.data);self.assertEqual(r.data['status'],'sent')
        self.assertFalse(r.data['actions']['change']);self.assertFalse(r.data['actions']['accept'])
        self.assertEqual(self.action('accept').status_code,403)
        self.grant('view','accept');r=self.action('accept');self.assertEqual(r.status_code,200,r.data);self.assertEqual(r.data['status'],'accepted')
        self.assertEqual(self.action('reject',reason='Teste').status_code,403)
        self.assertEqual(self.action('convert').status_code,403);self.no_effects()

    def test_reject_requires_specific_right_and_reason(self):
        self.grant('reject')
        self.assertEqual(self.action('reject').status_code,400)
        r=self.action('reject',reason='Cliente desistiu');self.assertEqual(r.status_code,200)
        self.assertTrue(Quote.objects.filter(pk=self.quote.pk).exists())
        self.assertEqual(QuoteEvent.objects.get().reason,'Cliente desistiu')
        self.assertEqual(self.client.delete(self.url(f'{self.quote.pk}/')).status_code,405)
        self.no_effects()

    def test_conversion_requires_both_permissions_and_creates_only_draft(self):
        self.state('accepted');self.grant('view','convert')
        self.assertEqual(self.action('convert').status_code,403)
        self.grant('view',sale_add=True);self.assertEqual(self.action('convert').status_code,403)
        self.grant('view','convert',sale_add=True)
        r=self.action('convert');self.assertEqual(r.status_code,200,r.data)
        sale=Sale.objects.get();self.assertEqual(sale.status,'draft');self.assertEqual(sale.total,100)
        self.no_effects()

    def test_conversion_replay_checks_rights_even_when_already_converted(self):
        self.state('accepted');self.grant('convert',sale_add=True)
        body={'request_id':str(uuid.uuid4()),'expected_version':self.quote.version}
        path=self.url(f'{self.quote.pk}/convert/')
        first=self.client.post(path,body,format='json');self.assertEqual(first.status_code,200)
        self.assertEqual(self.client.post(path,body,format='json').data['sale'],first.data['sale'])
        self.grant('convert');self.assertEqual(self.client.post(path,body,format='json').status_code,403)
        self.grant(sale_add=True);self.assertEqual(self.client.post(path,body,format='json').status_code,403)
        self.assertEqual(Sale.objects.count(),1)

    def test_print_requires_view_and_print_and_does_not_write(self):
        self.grant('print');self.assertEqual(self.client.get(self.url(f'{self.quote.pk}/print/')).status_code,403)
        self.grant('view','print')
        r=self.client.get(self.url(f'{self.quote.pk}/print/'));self.assertEqual(r.status_code,200)
        self.assertIn('Cliente proposta',r.content.decode());self.assertIn('no-store',r['Cache-Control'])
        self.assertFalse(QuoteEvent.objects.exists());self.assertFalse(QuoteOperation.objects.exists());self.no_effects()

    def test_options_are_minimal_scoped_and_not_full_catalog_access(self):
        self.grant('add')
        r=self.client.get(self.url('options/'));self.assertEqual(r.status_code,200)
        self.assertEqual(set(r.data['customers'][0]),{'id','name'})
        self.assertEqual(set(r.data['products'][0]),{'id','internal_code','name','sale_price'})
        self.assertIsInstance(r.data['products'][0]['sale_price'],str)
        self.assertEqual(len(r.data['products']),1);self.assertIn('no-store',r['Cache-Control'])
        self.assertEqual(self.client.get(f'/api/me/products/?store_id={self.store.pk}').status_code,403)
        self.grant('view');self.assertEqual(self.client.get(self.url('options/')).status_code,403)

    def test_customer_history_also_requires_quote_consultation(self):
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label='organizations',codename__in=['view_customer','view_customer_history']))
        base=f'/api/me/customers/{self.customer.pk}/history/?store_id={self.store.pk}'
        for suffix in ['&section=quotes',f'&section=quotes&record_id={self.quote.pk}']:
            self.assertEqual(self.client.get(base+suffix).status_code,403)
        summary=self.client.get(base).data
        self.assertFalse(summary['permissions']['quotes']);self.assertIsNone(summary['summary']['quotes'])
        self.grant('view')
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label='organizations',codename__in=['view_customer','view_customer_history']))
        self.assertEqual(self.client.get(base+'&section=quotes').status_code,200)
        self.assertEqual(self.client.get(base).data['summary']['quotes'],1)
        self.grant()
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label='organizations',codename__in=['view_customer','view_customer_history']))
        self.assertEqual(self.client.get(base+'&section=quotes').status_code,403)

    def test_service_permission_is_checked_before_replay_and_validation(self):
        with self.assertRaises(PermissionDenied):operate_quote(user=self.user,store=self.store,quote_id=self.quote.pk,action='send',request_id=uuid.uuid4(),digest='test',validated_values=lambda:{'expected_version':1})
        self.grant('send')
        identity=uuid.uuid4();kwargs=dict(user=self.user,store=self.store,quote_id=self.quote.pk,action='send',request_id=identity,digest='test',validated_values=lambda:{'expected_version':1})
        operate_quote(**kwargs);self.grant()
        with self.assertRaises(PermissionDenied):operate_quote(**kwargs)
        self.assertEqual(QuoteEvent.objects.count(),1)

    def test_group_and_direct_revocation_in_same_session(self):
        group=Group.objects.create(name='Propostas consulta');group.permissions.add(Permission.objects.get(content_type__app_label='sales',codename='view_quote'));self.user.groups.add(group)
        self.assertEqual(self.client.get(self.url()).status_code,200)
        group.permissions.clear();self.assertEqual(self.client.get(self.url()).status_code,403)
        self.grant('view');self.assertEqual(self.client.get(self.url()).status_code,200)
        self.grant();self.assertEqual(self.client.get(self.url()).status_code,403)

    def test_lifecycle_metadata_and_terminal_states(self):
        self.grant('view','change','send','accept','reject','convert','print',sale_add=True)
        draft=self.client.get(self.url(f'{self.quote.pk}/')).data['actions']
        self.assertTrue(draft['send']);self.assertFalse(draft['accept']);self.assertFalse(draft['convert'])
        self.state('sent');sent=self.client.get(self.url(f'{self.quote.pk}/')).data['actions']
        self.assertTrue(sent['accept']);self.assertFalse(sent['send'])
        self.state('accepted');self.assertTrue(self.client.get(self.url(f'{self.quote.pk}/')).data['actions']['convert'])
        self.action('reject',reason='Recusado');r=self.client.get(self.url(f'{self.quote.pk}/'))
        for key in ['change','send','accept','reject','convert']:self.assertFalse(r.data['actions'][key])
        self.assertTrue(r.data['actions']['print'])
        self.assertEqual(self.write(self.payload(expected_version=r.data['version']),self.quote).status_code,400)

    def test_expired_quote_and_wrong_state_remain_blocked(self):
        self.grant('view','send','accept','convert',sale_add=True)
        self.assertEqual(self.action('accept').status_code,400)
        self.assertEqual(self.action('convert').status_code,400)
        self.quote.valid_until=timezone.localdate()-timedelta(days=1);self.quote.save()
        self.assertEqual(self.action('send').status_code,400)
        self.assertFalse(self.client.get(self.url(f'{self.quote.pk}/')).data['actions']['send'])

    def test_other_store_objects_cannot_be_read_printed_or_changed(self):
        self.grant('view','change','print','send','convert',sale_add=True)
        other=Quote.objects.create(store=self.other,created_by=self.user,valid_until=timezone.localdate())
        for suffix in [f'{other.pk}/',f'{other.pk}/print/']:
            self.assertEqual(self.client.get(self.url(suffix)).status_code,404)
        self.assertEqual(self.action('send',other).status_code,403)
        self.assertEqual(self.write(self.payload(expected_version=1),other).status_code,403)
        self.assertEqual(self.client.get(self.url(store=self.other)).status_code,400)

    def test_inactive_membership_user_store_company_deny_operations(self):
        self.grant('view','add','send','print')
        for obj in [self.link,self.store,self.company,self.user]:
            obj.is_active=False;obj.save(update_fields=['is_active'])
            self.assertIn(self.client.get(self.url()).status_code,[400,403])
            self.assertIn(self.action('send').status_code,[400,403])
            obj.is_active=True;obj.save(update_fields=['is_active'])
        self.assertFalse(QuoteEvent.objects.exists())

    def test_csrf_is_required_and_status_cannot_be_forged(self):
        self.grant('view','add','change')
        browser=APIClient(enforce_csrf_checks=True);browser.force_login(self.user)
        self.assertEqual(browser.post(self.url(),self.payload(),format='json').status_code,403)
        self.assertEqual(browser.post(self.url(f'{self.quote.pk}/send/'),{},format='json').status_code,403)
        r=self.write(self.payload(status='accepted',sale=999,created_by=999,actions={'convert':True}))
        self.assertEqual(r.status_code,200);self.assertEqual(r.data['status'],'draft');self.assertIsNone(r.data['sale']);self.assertFalse(r.data['actions']['convert'])

    def test_admin_history_requires_quote_view_even_with_item_permission(self):
        from django.contrib import admin
        from django.test import RequestFactory
        self.user.is_staff=True;self.user.save(update_fields=['is_staff'])
        self.user.user_permissions.add(Permission.objects.get(content_type__app_label='sales',codename='view_quoteitem'))
        request=RequestFactory().get('/admin/');request.user=self.user
        handler=admin.site._registry[QuoteItem]
        self.assertFalse(handler.has_view_permission(request));self.assertEqual(handler.get_queryset(request).count(),0)
        self.grant('view');self.user.user_permissions.add(Permission.objects.get(content_type__app_label='sales',codename='view_quoteitem'))
        request=RequestFactory().get('/admin/');request.user=self.user
        self.assertTrue(handler.has_view_permission(request));self.assertEqual(handler.get_queryset(request).count(),1)
        self.assertFalse(handler.has_add_permission(request));self.assertFalse(handler.has_change_permission(request));self.assertFalse(handler.has_delete_permission(request))

    def test_anonymous_superuser_head_options_and_invalid_action(self):
        self.client.force_authenticate(None);self.assertEqual(self.client.get(self.url('access/')).status_code,403)
        self.client.force_authenticate(self.user);self.assertEqual(self.client.head(self.url()).status_code,403);self.assertEqual(self.client.options(self.url()).status_code,403)
        self.user.is_superuser=True;self.user.save(update_fields=['is_superuser'])
        self.assertEqual(self.client.head(self.url()).status_code,200);self.assertEqual(self.client.options(self.url()).status_code,200)
        self.assertEqual(self.action('invalid').status_code,400)
        access=self.client.get(self.url('access/'));self.assertTrue(access.data['actions']['convert']);self.assertIn('no-store',access['Cache-Control'])
