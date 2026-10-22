"""Permissões de vendas não são implícitas pelo perfil, staff ou acesso aos cadastros."""
import uuid
from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from rest_framework.test import APIClient
from accounts.models import StoreMembership
from organizations.models import Company, Store, Customer, Product, StockMovement
from .models import Sale, SaleItem, SalePayment, FinancialAccount, PaymentMethod, CheckoutRequest


class SaleAccessTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='sales-rights', password='test-only-password')
        self.company = Company.objects.create(name='Empresa')
        self.store = Store.objects.create(company=self.company, code='P1', name='Matriz')
        self.other = Store.objects.create(company=self.company, code='P2', name='Filial')
        self.link = StoreMembership.objects.create(user=self.user, store=self.store, role=StoreMembership.Role.MANAGER)
        self.customer = Customer.objects.create(store=self.store, name='Cliente')
        self.product = Product.objects.create(store=self.store, internal_code='P1', name='Produto', sale_price=100, cost_price=45, stock_quantity=10)
        self.other_product = Product.objects.create(store=self.other, internal_code='P2', name='Outro')
        self.sale = Sale.objects.create(store=self.store, created_by=self.user)
        self.item = SaleItem.objects.create(sale=self.sale, product=self.product, quantity=1)
        self.account = FinancialAccount.objects.create(store=self.store, code='bank', name='Banco')
        self.method = PaymentMethod.objects.create(store=self.store, code='pix', name='Pix', kind='pix')
        SalePayment.objects.create(sale=self.sale, account=self.account, method=self.method, amount=100, first_due_date=date.today())
        self.client = APIClient(); self.client.force_authenticate(self.user)

    def grant(self, *actions):
        self.user.user_permissions.set(Permission.objects.filter(content_type__app_label='sales', content_type__model='sale', codename__in=[a+'_sale' for a in actions]))

    def url(self, suffix='', store=None):
        return f'/api/me/sales/{suffix}?store_id={(store or self.store).pk}'

    def post(self, suffix, data=None):
        return self.client.post(self.url(suffix), data or {}, format='json')

    def payload(self, action='draft', sale_id=None):
        return {'request_id':str(uuid.uuid4()), 'action':action, 'sale_id':sale_id, 'notes':'Atendimento', 'discount_amount':'0',
            'items':[{'product_id':self.product.pk,'quantity':'1','unit_price':'100','discount_amount':'0'}],
            'payments':[{'method_id':self.method.pk,'account_id':self.account.pk,'amount':'100','first_due_date':str(date.today()),'confirmed':False}]}

    def test_staff_and_manager_without_permissions_are_denied(self):
        self.user.is_staff=True; self.user.save(update_fields=['is_staff'])
        for suffix in ['',f'{self.sale.pk}/','options/']:
            self.assertEqual(self.client.get(self.url(suffix)).status_code,403)
        for suffix,data in [('',{}),(f'{self.sale.pk}/finalize/',{}),(f'{self.sale.pk}/cancel/',{'reason':'Teste'}),('checkout/',self.payload())]:
            self.assertEqual(self.post(suffix,data).status_code,403)
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,10)
        self.assertFalse(StockMovement.objects.exists())

    def test_access_is_own_scoped_and_uncached(self):
        r=self.client.get(self.url('access/'));self.assertEqual(r.status_code,200)
        self.assertFalse(r.data['view']);self.assertIn('no-store',r['Cache-Control'])
        self.assertEqual(self.client.get(self.url('access/',self.other)).status_code,400)

    def test_view_only_flags_and_writes(self):
        self.grant('view')
        r=self.client.get(self.url(f'{self.sale.pk}/'));self.assertEqual(r.status_code,200)
        for flag in ['can_edit','can_finalize','can_cancel']:self.assertFalse(r.data[flag])
        self.assertEqual(self.post('',{}).status_code,403)
        self.assertEqual(self.client.patch(self.url(f'{self.sale.pk}/'),{'notes':'X'},format='json').status_code,403)
        self.assertEqual(self.post(f'{self.sale.pk}/items/',{'product_id':self.product.pk}).status_code,403)
        self.assertEqual(self.client.delete(self.url(f'{self.sale.pk}/items/{self.item.pk}/')).status_code,403)
        self.assertEqual(self.post(f'{self.sale.pk}/finalize/').status_code,403)
        self.assertEqual(self.post(f'{self.sale.pk}/cancel/',{'reason':'Teste'}).status_code,403)

    def test_add_without_view_can_create_but_not_list_or_edit(self):
        self.grant('add')
        self.assertEqual(self.post('',{'notes':'Nova'}).status_code,201)
        self.assertEqual(self.client.get(self.url()).status_code,403)
        self.assertEqual(self.client.get(self.url(f'{self.sale.pk}/')).status_code,403)
        self.assertEqual(self.post('checkout/',self.payload(sale_id=self.sale.pk)).status_code,403)
        self.assertEqual(self.post('checkout/',self.payload('complete')).status_code,403)

    def test_change_without_add_can_edit_header_items_and_checkout(self):
        self.grant('change')
        self.assertEqual(self.client.patch(self.url(f'{self.sale.pk}/'),{'notes':'Editada'},format='json').status_code,200)
        self.assertEqual(self.client.patch(self.url(f'{self.sale.pk}/items/{self.item.pk}/'),{'quantity':'2'},format='json').status_code,200)
        self.assertEqual(self.client.delete(self.url(f'{self.sale.pk}/items/{self.item.pk}/')).status_code,200)
        self.assertEqual(self.post(f'{self.sale.pk}/items/',{'product_id':self.product.pk,'quantity':'1'}).status_code,201)
        self.assertEqual(self.post('checkout/',self.payload(sale_id=self.sale.pk)).status_code,200)
        self.assertEqual(self.post('checkout/',self.payload()).status_code,403)

    def test_finalize_only_uses_saved_data_and_does_not_allow_checkout_replacement(self):
        self.grant('finalize')
        self.assertEqual(self.post('checkout/',self.payload('complete',self.sale.pk)).status_code,403)
        r=self.post(f'{self.sale.pk}/finalize/');self.assertEqual(r.status_code,200,r.data)
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,9)
        self.assertEqual(self.post(f'{self.sale.pk}/finalize/').status_code,200)
        self.assertEqual(StockMovement.objects.count(),1)

    def test_checkout_permissions_and_replay_are_checked_before_writes(self):
        self.grant('add','finalize')
        payload=self.payload('complete')
        r=self.post('checkout/',payload);self.assertEqual(r.status_code,200,r.data)
        sale_count=Sale.objects.count();movement_count=StockMovement.objects.count()
        self.assertEqual(self.post('checkout/',payload).data['id'],r.data['id'])
        self.grant('add')
        self.assertEqual(self.post('checkout/',payload).status_code,403)
        self.assertEqual(Sale.objects.count(),sale_count);self.assertEqual(StockMovement.objects.count(),movement_count)
        self.assertEqual(CheckoutRequest.objects.count(),1)

    def test_cancel_permission_does_not_grant_edit_or_physical_delete(self):
        self.grant('cancel')
        r=self.post(f'{self.sale.pk}/cancel/',{'reason':'Cliente desistiu'});self.assertEqual(r.status_code,200,r.data)
        self.assertTrue(Sale.objects.filter(pk=self.sale.pk).exists())
        self.assertEqual(self.client.delete(self.url(f'{self.sale.pk}/')).status_code,405)
        self.assertEqual(self.client.patch(self.url(f'{self.sale.pk}/'),{'notes':'X'},format='json').status_code,403)
        self.assertFalse(StockMovement.objects.exists())

    def test_completed_cancel_preserves_existing_staff_business_rule(self):
        self.grant('finalize','cancel')
        self.assertEqual(self.post(f'{self.sale.pk}/finalize/').status_code,200)
        self.assertEqual(self.post(f'{self.sale.pk}/cancel/',{'reason':'Devolução'}).status_code,403)
        self.user.is_staff=True;self.user.save(update_fields=['is_staff'])
        self.assertEqual(self.post(f'{self.sale.pk}/cancel/',{'reason':'Devolução'}).status_code,200)
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,10)

    def test_delete_sale_and_saleitem_permissions_do_not_authorize_cancellation(self):
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label='sales',codename__in=['delete_sale','add_saleitem','change_saleitem','delete_saleitem']))
        self.assertEqual(self.post(f'{self.sale.pk}/cancel/',{'reason':'Teste'}).status_code,403)
        self.assertEqual(self.post(f'{self.sale.pk}/items/',{'product_id':self.product.pk}).status_code,403)

    def test_options_are_minimal_and_independent_of_catalog_permissions(self):
        self.grant('add')
        r=self.client.get(self.url('options/'));self.assertEqual(r.status_code,200)
        self.assertEqual(set(r.data['customers'][0]),{'id','name'})
        self.assertEqual(set(r.data['products'][0]),{'id','internal_code','name','barcode','sale_price','stock_quantity'})
        self.assertEqual(len(r.data['products']),1)
        self.assertNotIn('balance',r.data['payment_options']['accounts'][0])
        self.assertIn('no-store',r['Cache-Control'])
        self.assertEqual(self.client.get(f'/api/me/products/?store_id={self.store.pk}').status_code,403)
        self.assertEqual(self.client.get(f'/api/me/customers/?store_id={self.store.pk}').status_code,403)

    def test_group_permissions_and_revocation_in_same_authenticated_client(self):
        group=Group.objects.create(name='Vendas consulta')
        group.permissions.add(Permission.objects.get(content_type__app_label='sales',codename='view_sale'))
        self.user.groups.add(group)
        self.assertEqual(self.client.get(self.url()).status_code,200)
        group.permissions.clear()
        self.assertEqual(self.client.get(self.url()).status_code,403)
        self.grant('view');self.assertEqual(self.client.get(self.url()).status_code,200)
        self.grant();self.assertEqual(self.client.get(self.url()).status_code,403)

    def test_membership_revocation_store_company_and_user_inactive(self):
        self.grant('view','add','change','finalize','cancel')
        for obj in [self.link,self.store,self.company,self.user]:
            obj.is_active=False;obj.save(update_fields=['is_active'])
            self.assertIn(self.client.get(self.url()).status_code,[400,403])
            self.assertIn(self.post(f'{self.sale.pk}/finalize/').status_code,[400,403])
            obj.is_active=True;obj.save(update_fields=['is_active'])
        self.assertEqual(self.client.get(self.url(store=self.other)).status_code,400)

    def test_cross_store_objects_cannot_be_operated(self):
        self.grant('view','change','finalize','cancel')
        other_sale=Sale.objects.create(store=self.other,created_by=self.user)
        for suffix in [f'{other_sale.pk}/finalize/',f'{other_sale.pk}/cancel/']:
            self.assertEqual(self.post(suffix,{'reason':'Teste'}).status_code,404)
        self.assertEqual(self.post('checkout/',self.payload(sale_id=other_sale.pk)).status_code,403) # lacks add? has change, draft lookup rejects other store

    def test_csrf_is_required_even_with_all_permissions(self):
        self.grant('add','change','finalize','cancel')
        client=APIClient(enforce_csrf_checks=True);client.force_login(self.user)
        self.assertEqual(client.post(self.url(),{},format='json').status_code,403)
        self.assertEqual(client.post(self.url('checkout/'),self.payload(),format='json').status_code,403)
        self.assertEqual(client.post(self.url(f'{self.sale.pk}/finalize/'),{},format='json').status_code,403)

    def test_anonymous_and_superuser(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url('access/')).status_code,403)
        self.user.is_superuser=True;self.user.save(update_fields=['is_superuser'])
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(self.url()).status_code,200)
        self.assertTrue(self.client.get(self.url('access/')).data['finalize'])

    def test_invalid_discriminators_do_not_create_or_replay(self):
        self.grant('add','change','finalize')
        for values in [[], {'action':'hack'}, {'action':'draft','sale_id':0}]:
            self.assertEqual(self.post('checkout/',values).status_code,400)
        self.assertEqual(Sale.objects.count(),1)

    def test_quote_conversion_needs_add_sale_even_on_replay(self):
        from .models import Quote, QuoteItem
        permission=Permission.objects.get(content_type__app_label="sales",codename="convert_quote")
        self.user.user_permissions.add(permission)
        quote=Quote.objects.create(store=self.store,created_by=self.user,valid_until=date.today())
        QuoteItem.objects.create(quote=quote,product=self.product,quantity=1,unit_price=100)
        quote.status='accepted';quote.save(_allow_transition=True)
        endpoint=f'/api/me/quotes/{quote.pk}/convert/?store_id={self.store.pk}'
        data={'request_id':str(uuid.uuid4()),'expected_version':quote.version}
        self.assertEqual(self.client.post(endpoint,data,format='json').status_code,403)
        self.assertEqual(Sale.objects.count(),1)
        self.grant('add');self.user.user_permissions.add(permission)
        self.assertEqual(self.client.post(endpoint,data,format='json').status_code,200)
        self.assertEqual(Sale.objects.count(),2)
        self.grant();self.user.user_permissions.add(permission)
        self.assertEqual(self.client.post(endpoint,data,format='json').status_code,403)
        self.assertEqual(Sale.objects.count(),2)

    def test_discount_and_prescription_endpoints_do_not_bypass_sale_permissions(self):
        for suffix,body in [(f'{self.sale.pk}/discount/request/',{'reason':'Autorização'}),
                (f'{self.sale.pk}/discount/1/decision/',{'action':'approve','reason':'Teste'})]:
            self.assertEqual(self.post(suffix,body).status_code,403)
        self.assertEqual(self.client.get(self.url(f'{self.sale.pk}/prescription-history/')).status_code,403)

    def test_update_and_create_cannot_forge_status_or_grant_permissions(self):
        self.grant('add','change')
        r=self.post('',{'status':'completed','can_finalize':True,'created_by':999,'permissions':['finalize_sale']})
        self.assertEqual(r.status_code,201)
        self.assertEqual(r.data['status'],'draft');self.assertFalse(r.data['can_finalize'])
        self.assertEqual(self.post(f'{self.sale.pk}/finalize/').status_code,403)

    def test_head_options_and_unsupported_verbs(self):
        self.assertEqual(self.client.head(self.url()).status_code,403)
        self.assertEqual(self.client.options(self.url()).status_code,403)
        self.grant('view')
        self.assertEqual(self.client.head(self.url()).status_code,200)
        self.assertEqual(self.client.options(self.url()).status_code,200)
        self.assertEqual(self.client.put(self.url(f'{self.sale.pk}/'),{},format='json').status_code,405)

    def test_status_change_is_impossible_without_finalize_and_cancel(self):
        self.grant('change')
        r=self.client.patch(self.url(f'{self.sale.pk}/'),{'status':'completed','completed_at':'2026-10-21'},format='json')
        self.assertEqual(r.status_code,200)
        self.sale.refresh_from_db();self.assertEqual(self.sale.status,'draft')
        self.assertFalse(StockMovement.objects.exists())
