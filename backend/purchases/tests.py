from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient
from sales import test_payments as fixtures
from sales.models import FinancialEntry, Receivable
from organizations.models import Product, Supplier, StockMovement
from .models import Purchase, PurchaseItem, PurchaseEvent, PurchaseStockMovement, PurchaseOperation
from organizations.stock_services import register_stock_movement


class PurchaseTests(TestCase):
    def setUp(self):
        fixtures.PaymentCheckoutTests.setUp(self)
        self.supplier=Supplier(store=self.store,name='Laboratório de teste',created_by=self.user,updated_by=self.user);self.supplier.save(_service=True)
        self.foreign_supplier=Supplier(store=self.other,name='Fornecedor filial',created_by=self.user,updated_by=self.user);self.foreign_supplier.save(_service=True)
        self.product2=Product.objects.create(store=self.store,internal_code='PG002',name='Lentes',sale_price='100',cost_price='10',stock_quantity='3')

    def grant(self,user=None,*codes):
        user=user or self.user
        codes=codes or ('view_purchase','add_purchase','change_purchase','receive_purchase')
        user.user_permissions.add(*Permission.objects.filter(content_type__app_label='purchases',codename__in=codes))
        for key in ('_perm_cache','_user_perm_cache','_group_perm_cache'):
            if hasattr(user,key):delattr(user,key)

    def path(self,id=None,store=None):return f'/api/me/purchases/{str(id)+"/" if id else ""}?store_id={(store or self.store).pk}'

    def data(self,**extra):return {'request_id':str(uuid4()),'action':'create','supplier_id':self.supplier.pk,'reference':'DOC-001','document_date':'2026-10-01','notes':'Conferência de teste','items':[{'product_id':self.product.pk,'quantity':'2.500','unit_cost':'12.34'}],**extra}

    def write(self,data,id=None,expected=200,store=None):
        response=self.client.post(self.path(id,store),data,format='json')
        self.assertEqual(response.status_code,expected,response.data)
        return response.data

    def create(self,**extra):self.grant();return self.write(self.data(**extra))

    def action(self,record,action='receive',expected=200,**extra):return self.write({'request_id':str(uuid4()),'action':action,'expected_version':record['version'],'confirmed':True,**extra},id=record['id'],expected=expected)

    def test_draft_total_rounds_half_up_and_has_no_stock_or_financial_effect(self):
        record=self.create(items=[{'product_id':self.product.pk,'quantity':'0.500','unit_cost':'0.01'},{'product_id':self.product2.pk,'quantity':'1','unit_cost':'10.00'}])
        self.assertEqual(record['total'],'10.01');self.assertEqual(record['items'][0]['total'],'0.01')
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,10)
        self.assertFalse(StockMovement.objects.exists());self.assertFalse(Receivable.objects.exists());self.assertFalse(FinancialEntry.objects.exists())

    def test_receipt_atomically_books_stock_links_supplier_snapshot_and_actor(self):
        record=self.create();received=self.action(record)
        self.assertEqual(received['status'],'received');self.assertEqual(received['total'],'30.85')
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,Decimal('12.500'));self.assertEqual(self.product.cost_price,0)
        movement=StockMovement.objects.get();self.assertEqual(movement.created_by,self.user);self.assertEqual(movement.balance_before,10);self.assertEqual(movement.balance_after,Decimal('12.500'))
        self.assertEqual(PurchaseStockMovement.objects.get().movement,movement)
        self.assertEqual(received['supplier_snapshot']['name'],self.supplier.name)
        self.assertFalse(FinancialEntry.objects.exists())

    def test_cost_update_is_explicit_and_preserves_sale_price(self):
        record=self.create();received=self.action(record,update_cost=True)
        self.product.refresh_from_db();self.assertEqual(self.product.cost_price,Decimal('12.34'));self.assertEqual(self.product.sale_price,700)
        self.assertTrue(received['updates_cost'])

    def test_draft_edit_replaces_items_and_requires_current_version(self):
        record=self.create();body=self.data(action='update',expected_version=record['version'],items=[{'product_id':self.product2.pk,'quantity':'3','unit_cost':'5'}])
        updated=self.write(body,id=record['id']);self.assertEqual(updated['total'],'15.00');self.assertEqual(PurchaseItem.objects.count(),1)
        body['request_id']=str(uuid4());self.write(body,id=record['id'],expected=400)
        self.assertFalse(StockMovement.objects.exists())
        self.write(self.data(action='create',expected_version=updated['version']),id=record['id'],expected=400)

    def test_retries_do_not_duplicate_drafts_or_received_stock(self):
        self.grant();body=self.data();record=self.write(body)
        self.assertEqual(self.write(body)['id'],record['id']);self.assertEqual(Purchase.objects.count(),1)
        body={'request_id':str(uuid4()),'action':'receive','expected_version':1,'confirmed':True}
        received=self.write(body,id=record['id']);self.assertEqual(self.write(body,id=record['id'])['status'],'received')
        self.assertEqual(StockMovement.objects.count(),1);self.assertEqual(PurchaseEvent.objects.count(),2)
        body['update_cost']=True;self.write(body,id=record['id'],expected=400)
        self.action(received,expected=400)

    def test_requires_explicit_confirmation_and_receive_permission(self):
        record=self.create();self.action(record,confirmed=False,expected=400)
        self.user.user_permissions.remove(Permission.objects.get(content_type__app_label='purchases',codename='receive_purchase'))
        for key in ('_perm_cache','_user_perm_cache','_group_perm_cache'):
            if hasattr(self.user,key):delattr(self.user,key)
        self.action(record,expected=403);self.assertFalse(StockMovement.objects.exists())

    def test_received_and_cancelled_purchases_are_immutable(self):
        record=self.create();received=self.action(record)
        self.action(received,'cancel',reason='Tentativa',expected=400)
        self.write(self.data(action='update',expected_version=received['version']),id=record['id'],expected=400)
        self.assertEqual(self.client.delete(self.path(record['id'])).status_code,405)
        with self.assertRaises(ValidationError):Purchase.objects.get().save(_service=True)
        with self.assertRaises(ValidationError):Purchase.objects.get().delete()
        event=PurchaseEvent.objects.first()
        with self.assertRaises(ValidationError):event.save(_service=True)
        link=PurchaseStockMovement.objects.get()
        with self.assertRaises(ValidationError):link.delete()

    def test_cancel_draft_requires_reason_and_frees_reference_without_stock(self):
        record=self.create();self.action(record,'cancel',reason='',expected=400)
        cancelled=self.action(record,'cancel',reason='Documento digitado errado')
        self.assertEqual(cancelled['status'],'cancelled');self.assertFalse(StockMovement.objects.exists())
        self.action(cancelled,expected=400)
        replacement=self.create();self.assertNotEqual(replacement['id'],record['id'])

    def test_duplicate_reference_and_product_are_rejected(self):
        self.create();self.write(self.data(reference=' doc-001 '),expected=400)
        lines=[{'product_id':self.product.pk,'quantity':'1','unit_cost':'1'}]*2
        self.write(self.data(reference='DOC-002',items=lines),expected=400)
        self.assertEqual(Purchase.objects.count(),1);self.assertEqual(PurchaseItem.objects.count(),1)

    def test_invalid_values_do_not_create_partial_purchase(self):
        self.grant()
        for quantity,cost in [('0','1'),('-1','1'),('1','-1'),('1.0001','1'),('1','1.001'),('NaN','1'),('1','Infinity')]:
            self.write(self.data(items=[{'product_id':self.product.pk,'quantity':quantity,'unit_cost':cost}]),expected=400)
        self.write(self.data(items=[]),expected=400)
        self.assertFalse(Purchase.objects.exists())

    def test_supplier_product_and_unit_scope_are_checked(self):
        self.grant();self.write(self.data(supplier_id=self.foreign_supplier.pk),expected=404)
        other=Product.objects.create(store=self.other,internal_code='OTHER',name='Outro',sale_price='1')
        self.write(self.data(items=[{'product_id':other.pk,'quantity':'1','unit_cost':'1'}]),expected=400)
        record=self.create();self.assertEqual(self.client.get(self.path(record['id'],self.other)).status_code,400)
        from accounts.models import StoreMembership
        StoreMembership.objects.create(user=self.user,store=self.other,role=StoreMembership.Role.SELLER)
        self.assertEqual(self.client.get(self.path(record['id'],self.other)).status_code,404)
        self.assertEqual(self.client.get(self.path(store=self.other)).data['count'],0)

    def test_inactive_supplier_or_product_blocks_receipt_without_stock_changes(self):
        record=self.create();Supplier.objects.filter(pk=self.supplier.pk).update(is_active=False)
        self.action(record,expected=404);Supplier.objects.filter(pk=self.supplier.pk).update(is_active=True)
        Product.objects.filter(pk=self.product.pk).update(is_active=False)
        self.action(record,expected=400);self.assertFalse(StockMovement.objects.exists())

    def test_mid_receipt_failure_rolls_back_all_stock_costs_links_and_status(self):
        record=self.create(items=[{'product_id':self.product.pk,'quantity':'1','unit_cost':'7'},{'product_id':self.product2.pk,'quantity':'2','unit_cost':'8'}])
        calls=0
        def fail_second(**kwargs):
            nonlocal calls
            calls+=1
            if calls==2:raise RuntimeError('Falha de teste')
            return register_stock_movement(**kwargs)
        with patch('purchases.services.register_stock_movement',side_effect=fail_second):
            with self.assertRaises(RuntimeError):self.action(record,update_cost=True)
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,10);self.assertEqual(self.product.cost_price,0)
        self.assertFalse(StockMovement.objects.exists());self.assertFalse(PurchaseStockMovement.objects.exists())
        self.assertEqual(Purchase.objects.get().status,'draft');self.assertEqual(Purchase.objects.get().version,1)

    def test_forged_fields_cannot_override_status_author_store_or_balances(self):
        record=self.create(store=self.other.pk,status='received',received_by=self.admin.pk,updates_cost=True,version=55,supplier_snapshot={'name':'Falso'})
        self.assertEqual(record['store'],self.store.pk);self.assertEqual(record['status'],'draft');self.assertEqual(record['version'],1)
        self.assertFalse(StockMovement.objects.exists())

    def test_permissions_staff_authentication_and_csrf(self):
        self.write(self.data(),expected=403);self.client.force_authenticate(self.admin);self.write(self.data(),expected=403)
        self.grant(self.admin,'view_purchase');response=self.client.get(self.path());self.assertEqual(response.status_code,200);self.assertFalse(response.data['can_create']);self.assertFalse(response.data['can_receive'])
        self.client.force_authenticate(self.user);self.grant()
        client=APIClient(enforce_csrf_checks=True);client.force_login(self.user)
        self.assertEqual(client.post(self.path(),self.data(),format='json').status_code,403)
        self.client.force_authenticate(None);self.assertEqual(self.client.get(self.path()).status_code,403)

    def test_revoked_access_and_foreign_request_id_are_denied(self):
        self.grant();body=self.data();self.write(body);self.grant(self.admin);self.client.force_authenticate(self.admin);self.write(body,expected=403)
        self.client.force_authenticate(self.user)
        from accounts.models import StoreMembership
        StoreMembership.objects.filter(user=self.user,store=self.store).update(is_active=False)
        self.assertEqual(self.client.get(self.path()).status_code,400)

    def test_private_cache_filters_and_supplier_copy_survive_later_edits(self):
        record=self.create();self.action(record)
        Supplier.objects.filter(pk=self.supplier.pk).update(name='Nome novo',is_active=False)
        response=self.client.get(self.path(record['id']))
        self.assertEqual(response['Cache-Control'],'no-store, private');self.assertEqual(response.data['supplier_name'],'Laboratório de teste')
        self.assertEqual(self.client.get(self.path()+'&status=received').data['count'],1)
        self.assertEqual(self.client.get(self.path()+'&status=draft').data['count'],0)
        self.assertEqual(self.client.get(self.path()+'&status=invalid').status_code,400)

    def test_stock_limit_rejection_rolls_back_receipt(self):
        record=self.create();Product.objects.filter(pk=self.product.pk).update(stock_quantity=Decimal('999999999.999'))
        self.action(record,expected=400)
        self.assertFalse(StockMovement.objects.exists());self.assertEqual(Purchase.objects.get().status,'draft')

    def test_receipt_uses_saved_items_and_ignores_forged_selection(self):
        record=self.create()
        received=self.action(record,supplier_id=self.foreign_supplier.pk,items=[{'product_id':self.product2.pk,'quantity':'999','unit_cost':'999'}],balance_after='999999',created_by=self.admin.pk)
        self.assertEqual(received['supplier_id'],self.supplier.pk);self.assertEqual(received['total'],'30.85')
        self.product.refresh_from_db();self.product2.refresh_from_db()
        self.assertEqual(self.product.stock_quantity,Decimal('12.500'));self.assertEqual(self.product2.stock_quantity,3)
        self.assertEqual(StockMovement.objects.get().quantity,Decimal('2.500'))


from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from .services import operate_purchase


@skipUnless(connection.vendor=='postgresql','Teste de locks exige PostgreSQL.')
class PurchaseConcurrencyTests(TransactionTestCase):
    setUp=PurchaseTests.setUp
    grant=PurchaseTests.grant
    path=PurchaseTests.path
    data=PurchaseTests.data
    write=PurchaseTests.write
    create=PurchaseTests.create

    def worker(self,uid,purchase_id,values,digest):
        close_old_connections()
        try:
            from organizations.models import Store
            return operate_purchase(user=get_user_model().objects.get(pk=uid),store=Store.objects.get(pk=self.store.pk),purchase_id=purchase_id,values=values,digest=digest).pk
        except ValidationError:return None
        finally:close_old_connections()

    def test_simultaneous_receipts_register_only_one_stock_entry(self):
        record=self.create();self.grant(self.admin)
        def send(uid):return self.worker(uid,record['id'],{'request_id':uuid4(),'action':'receive','expected_version':1,'confirmed':True},'receive')
        with ThreadPoolExecutor(max_workers=2) as pool:ids=list(pool.map(send,[self.user.pk,self.admin.pk]))
        self.assertEqual(sum(i is not None for i in ids),1)
        self.assertEqual(StockMovement.objects.count(),1);self.assertEqual(PurchaseStockMovement.objects.count(),1)
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,Decimal('12.500'))

    def test_simultaneous_retry_creates_only_one_draft(self):
        self.grant();values={'request_id':uuid4(),'action':'create','supplier_id':self.supplier.pk,'reference':'','items':[{'product_id':self.product.pk,'quantity':Decimal('1'),'unit_cost':Decimal('5')}]}
        def send(_):return self.worker(self.user.pk,None,values,'same-draft')
        with ThreadPoolExecutor(max_workers=2) as pool:ids=list(pool.map(send,range(2)))
        self.assertEqual(ids[0],ids[1]);self.assertEqual(Purchase.objects.count(),1);self.assertEqual(PurchaseItem.objects.count(),1)
