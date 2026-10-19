from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, RequestFactory
from rest_framework.test import APIClient
from sales import test_payments as fixtures
from .models import Supplier, SupplierEvent, SupplierOperation, StockMovement
from .supplier_api import operate_supplier
from .supplier_models import valid_document


class SupplierTests(TestCase):
    setUp=fixtures.PaymentCheckoutTests.setUp

    def grant(self,user=None,*codes):
        user=user or self.user
        codes=codes or ('view_supplier','add_supplier','change_supplier')
        user.user_permissions.add(*Permission.objects.filter(content_type__app_label='organizations',codename__in=codes))
        for key in ('_perm_cache','_user_perm_cache','_group_perm_cache'):
            if hasattr(user,key):delattr(user,key)

    def path(self,id=None,store=None):
        return f'/api/me/suppliers/{str(id)+"/" if id else ""}?store_id={(store or self.store).pk}'

    def values(self,**extra):
        return {'request_id':str(uuid4()),'action':'create','person_type':'company','name':'Fornecedor de teste','document':'12.ABC.345/01DE-35',**extra}

    def write(self,data=None,id=None,expected=200,store=None):
        response=self.client.post(self.path(id,store),data or self.values(),format='json')
        self.assertEqual(response.status_code,expected,response.data)
        return response.data

    def create(self,**extra):
        self.grant();return self.write(self.values(**extra))

    def action(self,record,action='update',expected=200,**extra):
        return self.write({'request_id':str(uuid4()),'action':action,'expected_version':record['version'],**extra},id=record['id'],expected=expected)

    def test_company_complete_data_and_alphanumeric_document(self):
        result=self.create(trade_name='Lentes Aurora',email='contato@example.test',contact_name='Maria',phone='41999990000',zip_code='83820-000',street='Rua de teste',address_number='12',address_complement='Sala 1',neighborhood='Centro',city='Fazenda Rio Grande',state='pr',notes='Laboratório')
        self.assertEqual(result['document'],'12ABC34501DE35');self.assertEqual(result['zip_code'],'83820000');self.assertEqual(result['state'],'PR')
        supplier=Supplier.objects.get();self.assertEqual(supplier.store,self.store);self.assertEqual(supplier.created_by,self.user)
        self.assertEqual(supplier.events.count(),1);self.assertFalse(StockMovement.objects.exists())

    def test_numeric_cnpj_and_cpf(self):
        self.grant()
        self.assertEqual(self.write(self.values(document='11.222.333/0001-81'))['document'],'11222333000181')
        self.assertEqual(self.write(self.values(person_type='individual',document='529.982.247-25'))['document'],'52998224725')
        self.assertTrue(valid_document('12ABC34501DE35','company'))
        self.assertFalse(valid_document('12ABC34501DE34','company'))

    def test_invalid_documents_are_400_without_creating_records(self):
        self.grant()
        for document in ['11111111111111','12ABC34501DE34','12ABC34501DEAB','abc','١١٢٢٢٣٣٣٠٠٠١٨١','12ABC34501DE35!','52998224725']:
            self.write(self.values(document=document),expected=400)
        for document in ['33333333333','11222333000181','52998224724','A52998224725']:
            self.write(self.values(person_type='individual',document=document),expected=400)
        self.assertFalse(Supplier.objects.exists())

    def test_document_optional_and_replay_does_not_duplicate_blank_document(self):
        self.grant();data=self.values(document='');first=self.write(data);second=self.write(data)
        self.assertEqual(first['id'],second['id']);self.assertEqual(Supplier.objects.count(),1);self.assertEqual(SupplierEvent.objects.count(),1)
        data['name']='Outro conteúdo';self.write(data,expected=400)
        self.write(self.values(document=''));self.assertEqual(Supplier.objects.count(),2)

    def test_duplicate_document_including_inactive_rejected_but_other_store_allowed(self):
        record=self.create();self.action(record,'archive',reason='Não utilizado')
        self.write(self.values(document='12abc34501de35'),expected=400)
        from accounts.models import StoreMembership
        StoreMembership.objects.create(user=self.user,store=self.other,role=StoreMembership.Role.SELLER)
        self.write(self.values(),store=self.other)
        self.assertEqual(Supplier.objects.count(),2)

    def test_edit_requires_version_and_preserves_store_author_status(self):
        record=self.create();changed=self.action(record,name='Novo nome',store=self.other.pk,created_by=self.admin.pk,is_active=False,version=99)
        self.assertEqual(changed['name'],'Novo nome');self.assertEqual(changed['version'],2);self.assertTrue(changed['is_active'])
        supplier=Supplier.objects.get();self.assertEqual(supplier.store,self.store);self.assertEqual(supplier.created_by,self.user)
        self.action(record,name='Tela antiga',expected=400)
        self.write({'request_id':str(uuid4()),'action':'update','name':'Sem versão'},id=record['id'],expected=400)

    def test_archive_restore_require_reason_and_keep_same_record(self):
        record=self.create();self.action(record,'archive',expected=400)
        inactive=self.action(record,'archive',reason='Sem negociação')
        self.assertFalse(inactive['is_active']);self.assertEqual(self.client.get(self.path()).data['count'],0)
        self.assertEqual(self.client.get(self.path()+'&status=inactive').data['count'],1)
        self.action(inactive,'restore',expected=400)
        active=self.action(inactive,'restore',reason='Retomada de compras')
        self.assertEqual(active['id'],record['id']);self.assertTrue(active['is_active']);self.assertEqual(len(active['events']),3)
        self.assertEqual(self.client.delete(self.path(record['id'])).status_code,405)
        with self.assertRaises(ValidationError):Supplier.objects.get().delete()

    def test_permissions_and_staff_are_not_bypass(self):
        self.client.get(self.path());self.write(expected=403)
        self.client.force_authenticate(self.admin);self.write(expected=403)
        self.client.force_authenticate(self.user);record=self.create()
        self.grant(self.admin,'view_supplier');self.client.force_authenticate(self.admin)
        response=self.client.get(self.path());self.assertEqual(response.status_code,200);self.assertFalse(response.data['can_create']);self.assertFalse(response.data['can_edit'])
        self.action(record,name='Tentativa',expected=403)
        self.client.force_authenticate(None);self.assertEqual(self.client.get(self.path()).status_code,403)

    def test_unit_scope_on_reads_writes_and_revocation(self):
        record=self.create()
        self.assertEqual(self.client.get(self.path(record['id'],self.other)).status_code,400)
        from accounts.models import StoreMembership
        StoreMembership.objects.create(user=self.user,store=self.other,role=StoreMembership.Role.SELLER)
        self.assertEqual(self.client.get(self.path(record['id'],self.other)).status_code,404)
        self.write({'request_id':str(uuid4()),'action':'update','expected_version':1,'name':'Troca'},id=record['id'],store=self.other,expected=404)
        StoreMembership.objects.filter(user=self.user,store=self.store).update(is_active=False)
        self.assertEqual(self.client.get(self.path()).status_code,400)

    def test_csrf_required_for_session_writes(self):
        self.grant();client=APIClient(enforce_csrf_checks=True);client.force_login(self.user)
        self.assertEqual(client.post(self.path(),self.values(),format='json').status_code,403)
        self.assertFalse(Supplier.objects.exists())

    def test_search_paging_and_invalid_filters(self):
        self.create()
        self.assertEqual(self.client.get(self.path()+'&search=12.ABC.345%2F01DE-35').data['count'],1)
        self.assertEqual(self.client.get(self.path()+'&search=..').data['count'],0)
        self.assertEqual(self.client.get(self.path()+'&status=oops').status_code,400)
        for i in range(26):self.write(self.values(document='',name=f'Fornecedor {i:02}'))
        first=self.client.get(self.path()).data;second=self.client.get(self.path()+'&page=2').data
        self.assertEqual(first['count'],27);self.assertEqual(len(first['results']),25);self.assertEqual(len(second['results']),2)
        self.assertFalse({r['id'] for r in first['results']} & {r['id'] for r in second['results']})

    def test_invalid_contact_address_and_name(self):
        self.grant()
        for bad in [{'email':'errado'},{'state':'ZZ'},{'zip_code':'12345'},{'name':'   '}]:
            self.write(self.values(**bad),expected=400)
        self.assertFalse(Supplier.objects.exists())

    def test_event_failure_rolls_back_supplier_and_operation(self):
        self.grant()
        with patch('organizations.supplier_api.SupplierEvent.objects.create',side_effect=RuntimeError('Falha de teste')):
            with self.assertRaises(RuntimeError):self.write()
        self.assertFalse(Supplier.objects.exists());self.assertFalse(SupplierOperation.objects.exists())

    def test_admin_only_reads_authorized_store_and_models_protect_operations(self):
        record=self.create();supplier=Supplier.objects.get();self.grant(self.admin)
        request=RequestFactory().get('/admin/');request.user=self.admin
        model_admin=admin.site._registry[Supplier]
        self.assertEqual(model_admin.get_queryset(request).count(),1)
        self.assertFalse(model_admin.has_add_permission(request));self.assertFalse(model_admin.has_change_permission(request,supplier));self.assertFalse(model_admin.has_delete_permission(request,supplier))
        with self.assertRaises(ValidationError):supplier.save()
        event=supplier.events.get()
        with self.assertRaises(ValidationError):event.save()
        with self.assertRaises(ValidationError):event.delete()

    def test_replay_belongs_to_original_user(self):
        self.grant();data=self.values();self.write(data)
        self.grant(self.admin);self.client.force_authenticate(self.admin)
        self.write(data,expected=403)


@skipUnless(connection.vendor=='postgresql','Teste de concorrência exige PostgreSQL.')
class SupplierConcurrencyTests(TransactionTestCase):
    setUp=fixtures.PaymentCheckoutTests.setUp
    grant=SupplierTests.grant

    def test_same_request_creates_one_supplier(self):
        self.grant();uid=self.user.pk;sid=self.store.pk
        values={'request_id':uuid4(),'action':'create','name':'Fornecedor concorrente','document':''}
        def worker(_):
            close_old_connections()
            try:
                from .models import Store
                return operate_supplier(user=get_user_model().objects.get(pk=uid),store=Store.objects.get(pk=sid),supplier_id=None,values=values,digest='same-payload').pk
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:ids=list(pool.map(worker,range(2)))
        self.assertEqual(ids[0],ids[1]);self.assertEqual(Supplier.objects.count(),1);self.assertEqual(SupplierEvent.objects.count(),1)
