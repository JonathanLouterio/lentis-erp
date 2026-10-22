from uuid import uuid4
from decimal import Decimal
from django.contrib.auth.models import Permission, Group
from django.core.exceptions import PermissionDenied
from django.test import TestCase, RequestFactory
from django.contrib import admin
from . import tests as fixtures
from . import test_payables as payable_fixtures
from .models import Purchase, PurchaseEvent, PayablePayment
from .services import operate_purchase
from .payable_services import pay_installment, reverse_payment
from organizations.models import StockMovement

class PurchasePermissionTests(TestCase):
    setUp=fixtures.PurchaseTests.setUp
    grant=fixtures.PurchaseTests.grant
    data=fixtures.PurchaseTests.data
    path=fixtures.PurchaseTests.path
    write=fixtures.PurchaseTests.write
    create=fixtures.PurchaseTests.create
    action=fixtures.PurchaseTests.action

    def only(self,*codes):
        self.user.user_permissions.remove(*Permission.objects.filter(content_type__app_label='purchases'))
        self.grant(self.user,*codes)

    def test_editor_cannot_receive_or_cancel(self):
        record=self.create();self.only('view_purchase','change_purchase')
        self.action(record,expected=403)
        self.action(record,'cancel',reason='Documento errado',expected=403)
        self.assertFalse(StockMovement.objects.exists());self.assertEqual(PurchaseEvent.objects.count(),1)
        saved=self.write(self.data(action='update',expected_version=1,notes='Revisado'),id=record['id'])
        self.assertEqual(saved['notes'],'Revisado')

    def test_receiver_without_edit_keeps_saved_items(self):
        record=self.create();original_cost=self.product.cost_price;self.only('view_purchase','receive_purchase')
        received=self.action(record,items=[{'product_id':self.product2.pk,'quantity':'999','unit_cost':'999'}])
        self.assertEqual(received['status'],'received');self.assertEqual(received['total'],record['total'])
        self.product.refresh_from_db();self.assertEqual(self.product.cost_price,original_cost)
        self.assertFalse(received['actions']['update']);self.assertFalse(received['actions']['receive'])

    def test_cost_update_requires_extra_permission_and_rolls_back(self):
        record=self.create();self.only('view_purchase','receive_purchase')
        self.action(record,update_cost=True,expected=403)
        self.assertFalse(StockMovement.objects.exists());self.assertEqual(PurchaseEvent.objects.count(),1)
        self.grant(self.user,'update_purchase_cost')
        self.action(record,update_cost=True)
        self.product.refresh_from_db();self.assertEqual(self.product.cost_price,Decimal('12.34'))

    def test_cancel_without_edit_requires_reason_and_moves_no_stock(self):
        record=self.create();self.only('view_purchase','cancel_purchase')
        self.action(record,'cancel',expected=400)
        result=self.action(record,'cancel',reason='Duplicado')
        self.assertEqual(result['status'],'cancelled');self.assertFalse(StockMovement.objects.exists())
        self.assertFalse(result['actions']['cancel'])

    def test_read_only_cannot_fetch_catalog_or_write(self):
        record=self.create();self.only('view_purchase')
        self.assertEqual(self.client.get(self.path(record['id'])).status_code,200)
        self.assertEqual(self.client.get(f'/api/me/purchases/options/?store_id={self.store.pk}').status_code,403)
        self.write(self.data(),expected=403)
        self.action(record,'cancel',reason='Teste',expected=403)

    def test_catalog_is_minimal_scoped_and_independent_from_full_catalogs(self):
        self.only('view_purchase','add_purchase')
        self.user.user_permissions.remove(*Permission.objects.filter(content_type__app_label='organizations'))
        response=self.client.get(f'/api/me/purchases/options/?store_id={self.store.pk}')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['results'],[{'id':self.supplier.pk,'name':self.supplier.name,'document':self.supplier.document}])
        self.assertEqual(set(response.data['products'][0]),{'id','internal_code','name','cost_price'})
        self.assertTrue(all(row['id'] in (self.product.pk,self.product2.pk) for row in response.data['products']))
        self.assertEqual(self.client.post(self.path(),self.data(),format='json').status_code,200)

    def test_view_is_required_even_with_action(self):
        self.only('receive_purchase','add_purchase')
        self.assertEqual(self.client.get(self.path()).status_code,403)
        self.write(self.data(),expected=403)
        response=self.client.get(f'/api/me/purchases/access/?store_id={self.store.pk}')
        self.assertEqual(response.status_code,200);self.assertFalse(any(response.data['purchases'].values()))

    def test_group_revocation_and_replay_recheck_current_right(self):
        record=self.create();self.only('view_purchase')
        group=Group.objects.create(name='Recebimento');permission=Permission.objects.get(content_type__app_label='purchases',codename='receive_purchase');group.permissions.add(permission);self.user.groups.add(group)
        body={'request_id':str(uuid4()),'action':'receive','expected_version':1,'confirmed':True}
        self.write(body,id=record['id']);self.user.has_perm('purchases.receive_purchase');group.permissions.clear()
        self.write(body,id=record['id'],expected=403)
        self.assertEqual(StockMovement.objects.count(),1)
        with self.assertRaises(PermissionDenied):operate_purchase(user=self.user,store=self.store,purchase_id=record['id'],values=body,digest='unused')

    def test_cost_permission_revoked_before_replay(self):
        record=self.create();body={'request_id':str(uuid4()),'action':'receive','expected_version':1,'confirmed':True,'update_cost':True}
        self.write(body,id=record['id'])
        self.user.user_permissions.remove(Permission.objects.get(content_type__app_label='purchases',codename='update_purchase_cost'))
        self.write(body,id=record['id'],expected=403);self.assertEqual(StockMovement.objects.count(),1)

    def test_no_rights_staff_inactive_and_foreign_store(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(self.path()).status_code,403)
        self.client.force_authenticate(self.user);self.grant()
        self.assertIn(self.client.get(f'/api/me/purchases/access/?store_id={self.other.pk}').status_code,(400,403))
        type(self.user).objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.client.get(self.path()).status_code,403)

    def test_malformed_action_never_writes(self):
        self.grant()
        for action in ([],{},None,'delete'):
            self.write(self.data(action=action),expected=403)
        self.assertFalse(Purchase.objects.exists())

class PayablePermissionTests(TestCase):
    setUp=payable_fixtures.PayablesTests.setUp
    grant_payables=payable_fixtures.PayablesTests.grant_payables
    path=payable_fixtures.PayablesTests.path
    write=payable_fixtures.PayablesTests.write
    payable_url=payable_fixtures.PayablesTests.payable_url
    post=payable_fixtures.PayablesTests.post
    plan_data=payable_fixtures.PayablesTests.plan_data
    plan=payable_fixtures.PayablesTests.plan
    pay_data=payable_fixtures.PayablesTests.pay_data
    pay=payable_fixtures.PayablesTests.pay
    reverse=payable_fixtures.PayablesTests.reverse

    def only(self,*codes):
        self.user.user_permissions.remove(*Permission.objects.filter(content_type__app_label='purchases'))
        self.grant_payables(self.user,list(codes))

    def test_read_only_has_history_without_bank_options(self):
        plan=self.plan();self.only('view_payableplan')
        response=self.client.get(self.payable_url('options/'))
        self.assertEqual(response.status_code,200);self.assertEqual(response.data['accounts'],[]);self.assertEqual(response.data['methods'],[])
        self.assertEqual(self.client.get(self.payable_url(f"{plan['id']}/")).status_code,200)
        self.pay(plan['installments'][0]['id'],expected=403)

    def test_payer_without_purchase_or_reversal_right(self):
        plan=self.plan();self.only('view_payableplan','pay_payable')
        paid=self.pay(plan['installments'][0]['id']);self.assertEqual(paid['paid'],'10.00')
        payment=PayablePayment.objects.get()
        self.reverse(payment.pk,expected=403)
        self.post('',self.plan_data(),403)
        self.assertEqual(self.client.get(f'/api/me/purchases/?store_id={self.store.pk}').status_code,403)

    def test_reverser_does_not_gain_payment_or_account_catalog(self):
        plan=self.plan();self.pay(plan['installments'][0]['id']);payment=PayablePayment.objects.get()
        self.only('view_payableplan','reverse_payable')
        result=self.reverse(payment.pk);self.assertEqual(result['paid'],'0.00')
        self.pay(plan['installments'][0]['id'],expected=403)
        self.assertEqual(self.client.get(self.payable_url('options/')).data['accounts'],[])

    def test_generation_requires_purchase_read_and_no_pay_right(self):
        self.only('view_payableplan','add_payableplan')
        self.post('',self.plan_data(),403)
        self.grant_payables(self.user,['view_purchase'])
        plan=self.plan();self.pay(plan['installments'][0]['id'],expected=403)
        self.assertFalse(plan['can_pay']);self.assertFalse(plan['can_reverse'])

    def test_payment_replay_is_denied_after_revocation(self):
        plan=self.plan();target=plan['installments'][0]['id'];body=self.pay_data()
        self.pay(target,body)
        self.user.has_perm('purchases.pay_payable')
        self.user.user_permissions.remove(Permission.objects.get(content_type__app_label='purchases',codename='pay_payable'))
        self.pay(target,body,expected=403)
        with self.assertRaises(PermissionDenied):pay_installment(user=self.user,store=self.store,installment_id=target,values=body)
        self.assertEqual(PayablePayment.objects.count(),1)

    def test_reversal_replay_is_denied_after_revocation(self):
        plan=self.plan();self.pay(plan['installments'][0]['id']);payment=PayablePayment.objects.get()
        body={'request_id':str(uuid4()),'reason':'Corrigir'};self.reverse(payment.pk,body)
        self.user.user_permissions.remove(Permission.objects.get(content_type__app_label='purchases',codename='reverse_payable'))
        self.reverse(payment.pk,body,expected=403)
        with self.assertRaises(PermissionDenied):reverse_payment(user=self.user,store=self.store,payment_id=payment.pk,values=body)
        self.assertEqual(PayablePayment.objects.count(),2)

    def test_technical_admin_permission_cannot_bypass_plan_read(self):
        plan=self.plan();self.pay(plan['installments'][0]['id'])
        self.admin.user_permissions.add(Permission.objects.get(content_type__app_label='purchases',codename='view_payablepayment'))
        request=RequestFactory().get('/admin/purchases/payablepayment/');request.user=self.admin
        model_admin=admin.site._registry[PayablePayment]
        self.assertFalse(model_admin.has_view_permission(request));self.assertFalse(model_admin.get_queryset(request).exists())

    def test_payer_options_do_not_expose_balances_without_permission(self):
        self.only('view_payableplan','pay_payable')
        self.user.user_permissions.remove(*Permission.objects.filter(content_type__app_label='sales',codename__in=['move_cash','view_financialaccount']))
        response=self.client.get(self.payable_url('options/'))
        self.assertEqual(response.status_code,200,response.data)
        self.assertTrue(response.data['accounts']);self.assertTrue(all('balance' not in a for a in response.data['accounts']))
        self.assertTrue(all(m['kind']!='cash' for m in response.data['methods']))
