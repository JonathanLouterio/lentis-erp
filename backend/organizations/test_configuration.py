from uuid import uuid4
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, RequestFactory
from rest_framework.test import APIClient

from accounts.models import StoreMembership
from .models import Company, Store, Customer, Product, ConfigurationEvent

User = get_user_model()
BASE = '/api/system/'


class SystemConfigurationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username='platform', password='test-password')
        self.user = User.objects.create_user(username='operator', is_staff=True, password='test-password')
        self.company = Company.objects.create(name='Ótica A')
        self.other = Company.objects.create(name='Ótica B')
        self.store = Store.objects.create(company=self.company, code='A01', name='Matriz')
        self.foreign_store = Store.objects.create(company=self.other, code='B01', name='Matriz')
        self.membership = StoreMembership.objects.create(user=self.user, store=self.store, role='manager')
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def create_company(self, **extra):
        return self.client.post(BASE+'companies/', {'name': 'Nova ótica', 'request_id': str(uuid4()), **extra}, format='json')

    def update_company(self, **extra):
        return self.client.patch(f'{BASE}companies/{self.company.pk}/', {'version': self.company.configuration_version, 'request_id': str(uuid4()), **extra}, format='json')

    def create_store(self, **extra):
        return self.client.post(BASE+'stores/', {'name': 'Nova unidade', 'code': 'NOV1', 'company_id': self.company.pk, 'request_id': str(uuid4()), **extra}, format='json')

    def test_multiple_companies_and_global_admin_without_membership(self):
        result = self.create_company(name='Ótica independente')
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(Company.objects.count(), 3)
        self.assertEqual(self.client.get(BASE+'companies/').data['count'], 3)
        self.assertEqual(self.client.get('/api/me/stores/').status_code, 200)
        self.assertEqual({x['company_name'] for x in self.client.get('/api/me/stores/').data}, {'Ótica A', 'Ótica B'})

    def test_ordinary_staff_and_model_permissions_do_not_grant_configuration(self):
        self.user.user_permissions.add(*Permission.objects.filter(content_type__model__in=['company','store']))
        self.client.force_authenticate(self.user)
        for url in [BASE+'companies/', BASE+'stores/?company_id='+str(self.company.pk), BASE+'history/?company_id='+str(self.company.pk), f'{BASE}companies/{self.company.pk}/', f'{BASE}stores/{self.store.pk}/']:
            with self.subTest(url=url): self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.create_company().status_code, 403)
        self.assertEqual(self.create_store().status_code, 403)
        self.assertEqual(self.update_company(name='Inválido').status_code, 403)

    def test_anonymous_cannot_read_or_write(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(BASE+'companies/').status_code, 403)
        self.assertEqual(self.create_company().status_code, 403)

    def test_revoked_global_admin_is_checked_fresh(self):
        User.objects.filter(pk=self.admin.pk).update(is_superuser=False)
        self.assertEqual(self.client.get(BASE+'companies/').status_code, 403)
        self.assertEqual(self.create_store().status_code, 403)

    def test_inactive_global_admin_is_denied(self):
        User.objects.filter(pk=self.admin.pk).update(is_active=False)
        self.assertEqual(self.update_company(name='Inválido').status_code, 403)

    def test_session_csrf_required_on_post_and_patch(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(BASE+'companies/', {'name':'Bloqueada','request_id':str(uuid4())}, format='json').status_code, 403)
        self.assertEqual(client.patch(f'{BASE}companies/{self.company.pk}/', {'name':'Bloqueada','version':1,'request_id':str(uuid4())}, format='json').status_code, 403)
        token = client.get('/api/auth/csrf/').json()['csrfToken']
        response = client.post(BASE+'companies/', {'name':'CSRF válido','request_id':str(uuid4())}, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 201, response.data)

    def test_contact_social_and_normalization(self):
        response = self.create_company(legal_name='Ótica LTDA', instagram='https://www.instagram.com/otica/', website='https://example.com', whatsapp='+55 (41) 99999-9999', state='pr')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['state'], 'PR')
        self.assertEqual(response.data['whatsapp'], '5541999999999')
        self.assertEqual(response.data['legal_name'], 'Ótica LTDA')
        self.assertIn('no-cache', response['Cache-Control'])

    def test_invalid_social_and_unknown_fields_do_not_write(self):
        for payload in [{'instagram':'javascript:alert(1)'}, {'website':'http://example.com'}, {'facebook':'https://user:secret@example.com'}, {'state':'ZZ'}, {'whatsapp':'abc'}, {'is_superuser':True}, {'name':' '}]:
            with self.subTest(payload=payload):
                self.assertEqual(self.create_company(**payload).status_code, 400)
        self.assertEqual(Company.objects.count(), 2)
        self.assertFalse(ConfigurationEvent.objects.exists())

    def test_required_fields_and_missing_entities(self):
        self.assertEqual(self.client.post(BASE+'companies/', {'request_id':str(uuid4())}, format='json').status_code, 400)
        self.assertEqual(self.create_company(request_id='invalid').status_code, 400)
        self.assertEqual(self.create_store(company_id=999999).status_code, 404)
        self.assertEqual(self.client.get(BASE+'companies/999999/').status_code, 404)
        self.assertEqual(self.client.get(BASE+'stores/').status_code, 400)
        self.assertEqual(self.client.get(BASE+'history/').status_code, 400)

    def test_retry_same_operation_returns_original_without_duplicate(self):
        request_id=str(uuid4())
        first=self.create_company(request_id=request_id)
        second=self.create_company(request_id=request_id)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.data, second.data)
        self.assertEqual(ConfigurationEvent.objects.count(), 1)
        conflict=self.create_company(request_id=request_id, name='Outro conteúdo')
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(Company.objects.count(), 3)

    def test_update_retry_and_stale_version(self):
        request_id=str(uuid4())
        first=self.update_company(request_id=request_id, name='Alterada')
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(first.data['version'], 2)
        self.assertEqual(self.update_company(request_id=request_id, name='Alterada').data, first.data)
        self.assertEqual(self.update_company(name='Desatualizada').status_code, 409)
        self.company.refresh_from_db()
        self.assertEqual(self.company.name, 'Alterada')
        self.assertEqual(ConfigurationEvent.objects.count(), 1)

    def test_missing_version_is_rejected(self):
        response=self.client.patch(f'{BASE}companies/{self.company.pk}/', {'name':'X','request_id':str(uuid4())}, format='json')
        self.assertEqual(response.status_code, 409)

    def test_idempotency_key_belongs_to_actor(self):
        key=str(uuid4());self.create_company(request_id=key)
        other_admin=User.objects.create_superuser(username='second-admin')
        self.client.force_authenticate(other_admin)
        self.assertEqual(self.create_company(request_id=key).status_code, 409)

    def test_create_unit_records_company_and_stock_rule(self):
        response=self.create_store(code='new-1', allow_negative_stock=False, address='Rua das flores, 10', city='Curitiba', state='pr')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['code'], 'NEW-1')
        self.assertFalse(response.data['allow_negative_stock'])
        event=ConfigurationEvent.objects.get()
        self.assertEqual(event.company_id, self.company.pk)
        self.assertEqual(event.store_id, response.data['id'])
        self.assertEqual(event.actor_id, self.admin.pk)

    def test_global_unit_code_uniqueness(self):
        self.assertEqual(self.create_store(code=self.foreign_store.code).status_code, 400)
        self.assertEqual(Store.objects.count(), 2)
        self.assertFalse(ConfigurationEvent.objects.exists())

    def test_unit_cannot_change_company_in_api_or_model(self):
        response=self.client.patch(f'{BASE}stores/{self.store.pk}/', {'company_id':self.other.pk,'version':1,'request_id':str(uuid4())}, format='json')
        self.assertEqual(response.status_code, 400)
        self.store.company=self.other
        with self.assertRaises(ModelValidationError): self.store.save()
        self.store.refresh_from_db();self.assertEqual(self.store.company_id, self.company.pk)

    def test_company_deactivation_revokes_existing_session_and_keeps_history(self):
        customer=Customer.objects.create(store=self.store, name='Cliente preservado')
        session_client=APIClient();session_client.force_login(self.user)
        self.assertEqual(len(session_client.get('/api/me/stores/').data), 1)
        self.assertEqual(self.update_company(is_active=False).status_code, 200)
        self.assertEqual(session_client.get('/api/me/stores/').data, [])
        self.assertTrue(Customer.objects.filter(pk=customer.pk).exists())
        self.membership.refresh_from_db();self.assertTrue(self.membership.is_active)
        self.client.force_authenticate(self.admin)
        self.company.refresh_from_db()
        self.assertEqual(self.update_company(is_active=True).status_code, 200)
        self.assertEqual(len(session_client.get('/api/me/stores/').data), 1)

    def test_inactive_company_blocks_new_or_reactivated_unit(self):
        Company.objects.filter(pk=self.company.pk).update(is_active=False)
        self.assertEqual(self.create_store().status_code, 400)
        Store.objects.filter(pk=self.store.pk).update(is_active=False)
        response=self.client.patch(f'{BASE}stores/{self.store.pk}/', {'is_active':True,'version':1,'request_id':str(uuid4())}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_admin_is_read_only_and_hidden_from_staff(self):
        request=RequestFactory().get('/admin/');request.user=self.admin
        for model in [Company,Store,ConfigurationEvent]:
            view=admin.site._registry[model]
            self.assertTrue(view.has_view_permission(request))
            self.assertFalse(view.has_change_permission(request))
            self.assertFalse(view.has_add_permission(request))
            self.assertFalse(view.has_delete_permission(request))
            staff_request=RequestFactory().get('/admin/');staff_request.user=self.user
            self.assertFalse(view.has_view_permission(staff_request))
            self.assertFalse(view.get_queryset(staff_request).exists())

    def test_delete_is_not_supported(self):
        self.assertEqual(self.client.delete(f'{BASE}companies/{self.company.pk}/').status_code, 405)
        self.assertEqual(self.client.delete(f'{BASE}stores/{self.store.pk}/').status_code, 405)

    def test_audit_failure_rolls_back_configuration(self):
        with patch('organizations.configuration_api.ConfigurationEvent.objects.create', side_effect=RuntimeError('storage failure')):
            with self.assertRaises(RuntimeError): self.update_company(name='Não persistir')
        self.company.refresh_from_db()
        self.assertEqual(self.company.name, 'Ótica A')
        self.assertEqual(self.company.configuration_version, 1)

    def test_audit_values_and_company_scope(self):
        response=self.update_company(name='Ótica A atualizada')
        self.assertEqual(response.status_code, 200)
        events=self.client.get(BASE+'history/', {'company_id':self.company.pk}).data
        self.assertEqual(events['count'], 1)
        self.assertEqual(events['results'][0]['changes']['name'], {'before':'Ótica A','after':'Ótica A atualizada'})
        self.assertEqual(self.client.get(BASE+'history/', {'company_id':self.other.pk}).data['count'], 0)
        self.assertEqual(len(self.client.get(BASE+'stores/', {'company_id':self.company.pk}).data['results']), 1)

    def test_search_pagination_and_bad_queries(self):
        Company.objects.bulk_create([Company(name=f'Rede {i:02}') for i in range(30)])
        first=self.client.get(BASE+'companies/', {'q':'Rede'}).data
        second=self.client.get(BASE+'companies/', {'q':'Rede','page':2}).data
        self.assertEqual(first['count'], 30);self.assertTrue(first['has_next'])
        self.assertEqual(len(first['results']), 25);self.assertEqual(len(second['results']), 5)
        self.assertFalse(set(x['id'] for x in first['results']) & set(x['id'] for x in second['results']))
        for query in [{'page':0},{'page':'x'},{'company_id':2**70}]:
            self.assertEqual(self.client.get(BASE+'companies/', query).status_code, 400)

    def test_membership_options_include_company_identity(self):
        options=self.client.get('/api/me/user-management/options/').data['stores']
        self.assertEqual({x['company_name'] for x in options}, {'Ótica A','Ótica B'})


class MultipleCompanyIsolationTests(TestCase):
    def setUp(self):
        self.company=Company.objects.create(name='Ótica autorizada')
        self.other=Company.objects.create(name='Ótica independente')
        self.store=Store.objects.create(company=self.company,code='ISO1',name='Matriz')
        self.foreign=Store.objects.create(company=self.other,code='ISO2',name='Matriz')
        self.user=User.objects.create_user(username='isolated')
        self.user.user_permissions.set(Permission.objects.filter(content_type__app_label__in=['organizations','sales','purchases']))
        self.membership=StoreMembership.objects.create(user=self.user,store=self.store,role='manager')
        self.client=APIClient();self.client.force_authenticate(self.user)

    def test_guessed_foreign_unit_is_denied_in_every_operational_module(self):
        endpoints=['customers/','products/','stock-movements/','prescriptions/','prescriptions/customers/','suppliers/','sales/','sales/options/','quotes/','quotes/options/','service-orders/','purchases/','purchases/options/','payables/','payables/options/','receivables/','cash/','cash/options/','dashboard/','reports/','reports/options/']
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                response=self.client.get('/api/me/'+endpoint, {'store_id':self.foreign.pk})
                self.assertIn(response.status_code,[400,403,404], getattr(response,'data',None))

    def test_only_explicit_membership_appears_and_revocation_is_immediate(self):
        stores=self.client.get('/api/me/stores/').data
        self.assertEqual([row['company_id'] for row in stores], [self.company.pk])
        self.membership.is_active=False;self.membership.save()
        self.assertEqual(self.client.get('/api/me/stores/').data, [])

    def test_foreign_customer_and_product_detail_do_not_leak(self):
        customer=Customer.objects.create(store=self.foreign,name='Segredo outra ótica')
        product=Product.objects.create(store=self.foreign,internal_code='PRIVATE',name='Produto secreto')
        for path in [f'customers/{customer.pk}/',f'customers/{customer.pk}/history/',f'products/{product.pk}/']:
            with self.subTest(path=path):
                response=self.client.get('/api/me/'+path,{'store_id':self.store.pk})
                self.assertIn(response.status_code,[400,403,404])
                self.assertNotIn('Segredo',str(response.data))

    def test_exports_and_print_reject_foreign_company(self):
        for export in ['csv','print']:
            response=self.client.get('/api/me/reports/',{'store_id':self.foreign.pk,'report':'receivables','export':export})
            self.assertIn(response.status_code,[400,403,404])
        self.assertEqual(self.client.get('/api/me/reports/options/',{'store_id':self.store.pk}).status_code,200)

    def test_customer_listing_stays_inside_selected_unit(self):
        own=Customer.objects.create(store=self.store,name='Autorizado')
        Customer.objects.create(store=self.foreign,name='Não autorizado')
        response=self.client.get('/api/me/customers/',{'store_id':self.store.pk})
        self.assertEqual(response.status_code,200)
        self.assertEqual([row['id'] for row in response.data],[own.pk])


    def test_cross_company_writes_do_not_create_or_change_records(self):
        from sales.models import Sale, SaleItem
        foreign_customer=Customer.objects.create(store=self.foreign,name='Cliente de outra ótica')
        foreign_product=Product.objects.create(store=self.foreign,internal_code='FORBIDDEN',name='Produto de outra ótica')
        response=self.client.post(f'/api/me/customers/?store_id={self.foreign.pk}',{'name':'Não criar'},format='json')
        self.assertEqual(response.status_code,400)
        self.assertFalse(Customer.objects.filter(name='Não criar').exists())
        response=self.client.post(f'/api/me/sales/?store_id={self.store.pk}',{'customer_id':foreign_customer.pk},format='json')
        self.assertEqual(response.status_code,400)
        self.assertFalse(Sale.objects.exists())
        sale=Sale.objects.create(store=self.store,created_by=self.user)
        response=self.client.post(f'/api/me/sales/{sale.pk}/items/?store_id={self.store.pk}',{'product_id':foreign_product.pk},format='json')
        self.assertEqual(response.status_code,400)
        self.assertFalse(SaleItem.objects.exists())

    def test_cross_company_supplier_cannot_be_used_for_purchase(self):
        from organizations.models import Supplier
        from purchases.models import Purchase
        supplier=Supplier(store=self.foreign,name='Fornecedor de outra ótica',created_by=self.user,updated_by=self.user);supplier.save(_service=True)
        product=Product.objects.create(store=self.store,internal_code='OWN',name='Produto da unidade')
        payload={'request_id':str(uuid4()),'action':'create','supplier_id':supplier.pk,'items':[{'product_id':product.pk,'quantity':'1','unit_cost':'10.00'}]}
        response=self.client.post(f'/api/me/purchases/?store_id={self.store.pk}',payload,format='json')
        self.assertEqual(response.status_code,404)
        self.assertFalse(Purchase.objects.exists())


class ConfigurationMigrationTests(TransactionTestCase):
    def test_existing_company_unit_and_membership_survive_migration(self):
        old=('organizations','0010_alter_supplier_options')
        new=('organizations','0011_configurationevent_alter_company_options_and_more')
        executor=MigrationExecutor(connection)
        executor.migrate([old])
        try:
            apps=executor.loader.project_state([old]).apps
            CompanyBefore=apps.get_model('organizations','Company')
            StoreBefore=apps.get_model('organizations','Store')
            company=CompanyBefore.objects.create(name='Empresa legada')
            unit=StoreBefore.objects.create(company=company,code='LEGACY',name='Matriz antiga')
            user=User.objects.create_user(username='legacy-member')
            membership=StoreMembership.objects.create(user=user,store_id=unit.pk,role='seller')
            executor=MigrationExecutor(connection);executor.migrate([new])
            current=executor.loader.project_state([new]).apps
            CompanyAfter=current.get_model('organizations','Company');StoreAfter=current.get_model('organizations','Store')
            self.assertEqual(CompanyAfter.objects.get(pk=company.pk).name,'Empresa legada')
            self.assertEqual(StoreAfter.objects.get(pk=unit.pk).company_id,company.pk)
            self.assertEqual(StoreAfter.objects.get(pk=unit.pk).configuration_version,1)
            self.assertEqual(StoreMembership.objects.get(pk=membership.pk).store_id,unit.pk)
            self.assertTrue(StoreMembership.objects.get(pk=membership.pk).is_active)
            CompanyAfter.objects.create(name='Segunda ótica')
            self.assertEqual(CompanyAfter.objects.count(),2)
        finally:
            executor=MigrationExecutor(connection);executor.migrate(executor.loader.graph.leaf_nodes())


from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from django.db import close_old_connections


@skipUnless(connection.vendor == 'postgresql', 'Exige bloqueios reais do PostgreSQL.')
class ConfigurationConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.admins=[User.objects.create_superuser(username=f'config-admin-{i}') for i in range(2)]
        self.company=Company.objects.create(name='Concorrência')

    def parallel(self, callback, same_actor=False):
        barrier=Barrier(2)
        def work(index):
            close_old_connections()
            try:
                client=APIClient();client.force_authenticate(User.objects.get(pk=self.admins[0 if same_actor else index].pk))
                barrier.wait(timeout=10)
                return callback(client,index)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=[pool.submit(work,i) for i in range(2)]
            return [result.result(timeout=30) for result in results]

    def test_concurrent_updates_reject_stale_version(self):
        results=self.parallel(lambda client,i:client.patch(f'{BASE}companies/{self.company.pk}/', {'name':f'Edição {i}','version':1,'request_id':str(uuid4())},format='json').status_code)
        self.assertEqual(sorted(results),[200,409])
        self.assertEqual(ConfigurationEvent.objects.count(),1)
        self.company.refresh_from_db();self.assertEqual(self.company.configuration_version,2)

    def test_concurrent_retry_creates_only_one_company(self):
        payload={'name':'Uma só criação','request_id':str(uuid4())}
        results=self.parallel(lambda client,i:client.post(BASE+'companies/',payload,format='json'),same_actor=True)
        self.assertEqual([response.status_code for response in results],[201,201])
        self.assertEqual(results[0].data['id'],results[1].data['id'])
        self.assertEqual(ConfigurationEvent.objects.count(),1)

    def test_concurrent_creation_with_same_code_is_atomic(self):
        results=self.parallel(lambda client,i:client.post(BASE+'stores/', {'name':'Nova','code':'UNIQUE','company_id':self.company.pk,'request_id':str(uuid4())},format='json').status_code)
        self.assertEqual(sorted(results),[201,400])
        self.assertEqual(Store.objects.filter(code='UNIQUE').count(),1)
        self.assertEqual(ConfigurationEvent.objects.count(),1)
