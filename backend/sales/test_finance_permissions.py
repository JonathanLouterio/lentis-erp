import uuid
from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission, Group
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from rest_framework.test import APIClient
from accounts.models import StoreMembership
from organizations.models import Company, Store, Product, StockMovement
from .models import CashSession, CashPosting, FinancialAccount, PaymentMethod, Sale, SaleItem, SalePayment, Receivable, FinancialEntry
from .cash_services import open_cash, move_cash, close_cash
from .services import finalize_sale


class FinancePermissionTests(TestCase):
    def setUp(self):
        User=get_user_model()
        self.user=User.objects.create_user(username='cash-rights',password='test-only-password')
        self.owner=User.objects.create_user(username='other-owner')
        self.company=Company.objects.create(name='Empresa')
        self.store=Store.objects.create(company=self.company,code='C1',name='Matriz')
        self.other=Store.objects.create(company=self.company,code='C2',name='Filial')
        self.link=StoreMembership.objects.create(user=self.user,store=self.store,role='manager')
        StoreMembership.objects.create(user=self.owner,store=self.store,role='seller')
        self.cash=FinancialAccount.objects.create(store=self.store,code='cash',name='Caixa')
        self.bank=FinancialAccount.objects.create(store=self.store,code='bank',name='Banco')
        self.pix=PaymentMethod.objects.create(store=self.store,code='pix',name='Pix',kind='pix')
        self.money=PaymentMethod.objects.create(store=self.store,code='cash',name='Dinheiro',kind='cash')
        self.session=CashSession.objects.create(account=self.cash,opened_by=self.user,opening_amount=100,opening_request=uuid.uuid4())
        self.product=Product.objects.create(store=self.store,internal_code='CF1',name='Produto',sale_price=50,stock_quantity=10)
        self.sale=Sale.objects.create(store=self.store,created_by=self.user)
        SaleItem.objects.create(sale=self.sale,product=self.product,quantity=1)
        SalePayment.objects.create(sale=self.sale,method=self.pix,account=self.bank,amount=50,first_due_date=date.today())
        finalize_sale(user=self.user,sale_id=self.sale.pk)
        self.receivable=Receivable.objects.get(payment__sale=self.sale)
        self.client=APIClient();self.client.force_authenticate(self.user)

    def grant(self,*codes):
        self.user.user_permissions.set(Permission.objects.filter(content_type__app_label='sales',codename__in=codes))

    def url(self,path,store=None):return f'/api/me/{path}?store_id={(store or self.store).pk}'
    def post(self,path,data):return self.client.post(self.url(path),data,format='json')
    def receipt(self,**extra):return {'request_id':str(uuid.uuid4()),'amount':'10','account_id':self.bank.pk,'method_id':self.pix.pk,**extra}
    def move(self,**extra):return {'request_id':str(uuid.uuid4()),'kind':'supply','amount':'10','reason':'Troco',**extra}
    def close(self,**extra):return {'request_id':str(uuid.uuid4()),'counted_amount':'100','note':'',**extra}

    def test_owner_manager_staff_do_not_grant_cash_or_receipt_permissions(self):
        self.user.is_staff=True;self.user.save(update_fields=['is_staff'])
        for path in ['cash/','cash/options/',f'cash/{self.session.pk}/postings/','receivables/','sales/payment-options/']:
            self.assertEqual(self.client.get(self.url(path)).status_code,403)
        self.assertEqual(self.post(f'cash/{self.session.pk}/postings/',self.move()).status_code,403)
        self.assertEqual(self.post(f'cash/{self.session.pk}/close/',self.close()).status_code,403)
        self.assertEqual(self.post(f'receivables/{self.receivable.pk}/receive/',self.receipt()).status_code,403)
        self.assertFalse(CashPosting.objects.exists());self.assertFalse(FinancialEntry.objects.exists())

    def test_readonly_cash_flags_and_immutable_history(self):
        self.grant('view_cashsession')
        r=self.client.get(self.url(f'cash/{self.session.pk}/'));self.assertEqual(r.status_code,200)
        for key in ['can_operate','can_move','can_close']:self.assertFalse(r.data[key])
        self.assertEqual(self.post(f'cash/{self.session.pk}/postings/',self.move()).status_code,403)
        self.assertEqual(self.post(f'cash/{self.session.pk}/close/',self.close()).status_code,403)
        self.assertEqual(self.client.delete(self.url(f'cash/{self.session.pk}/')).status_code,405)

    def test_open_without_view_does_not_grant_listing_move_or_close(self):
        self.grant('add_cashsession')
        second=FinancialAccount.objects.create(store=self.store,code='cash2',name='Outro',is_cash_box=True)
        body={'request_id':str(uuid.uuid4()),'account_id':second.pk,'amount':'0'}
        self.assertEqual(self.post('cash/',body).status_code,200)
        self.assertEqual(self.post('cash/',body).status_code,200)
        self.assertEqual(self.client.get(self.url('cash/')).status_code,403)
        self.assertEqual(self.post(f'cash/{self.session.pk}/postings/',self.move()).status_code,403)
        self.grant();self.assertEqual(self.post('cash/',body).status_code,403)
        self.assertEqual(CashSession.objects.count(),2)

    def test_move_and_close_are_independent(self):
        self.grant('move_cash')
        body=self.move();self.assertEqual(self.post(f'cash/{self.session.pk}/postings/',body).status_code,200)
        self.assertEqual(self.post(f'cash/{self.session.pk}/postings/',body).status_code,200)
        self.assertEqual(CashPosting.objects.count(),1)
        self.assertEqual(self.post(f'cash/{self.session.pk}/close/',self.close()).status_code,403)
        self.grant('close_cash')
        self.assertEqual(self.post(f'cash/{self.session.pk}/postings/',body).status_code,403)
        self.assertEqual(self.post(f'cash/{self.session.pk}/close/',self.close(counted_amount='110')).status_code,200)

    def test_manage_other_cash_is_additional_not_a_replacement(self):
        CashSession.objects.filter(pk=self.session.pk).update(opened_by=self.owner)
        self.grant('manage_cash')
        self.assertEqual(self.post(f'cash/{self.session.pk}/postings/',self.move()).status_code,403)
        self.grant('move_cash','close_cash')
        self.assertEqual(self.post(f'cash/{self.session.pk}/postings/',self.move()).status_code,403)
        self.grant('move_cash','close_cash','manage_cash')
        self.assertEqual(self.post(f'cash/{self.session.pk}/postings/',self.move()).status_code,200)
        self.assertEqual(self.post(f'cash/{self.session.pk}/close/',self.close(counted_amount='110')).status_code,200)

    def test_service_entrypoints_also_require_fresh_permissions(self):
        with self.assertRaises(PermissionDenied):move_cash(user=self.user,store=self.store,session_id=self.session.pk,kind='supply',amount=Decimal('1'),reason='Troco',request_id=uuid.uuid4())
        with self.assertRaises(PermissionDenied):close_cash(user=self.user,store=self.store,session_id=self.session.pk,counted_amount=Decimal('100'),note='',request_id=uuid.uuid4())
        with self.assertRaises(PermissionDenied):open_cash(user=self.user,store=self.store,account_id=self.cash.pk,amount=Decimal('0'),note='',request_id=uuid.uuid4())

    def test_nonstaff_can_receive_and_replay_but_revoked_permission_blocks(self):
        self.grant('receive_receivable')
        body=self.receipt()
        self.assertEqual(self.post(f'receivables/{self.receivable.pk}/receive/',body).status_code,200)
        self.assertEqual(self.post(f'receivables/{self.receivable.pk}/receive/',body).status_code,200)
        self.assertEqual(FinancialEntry.objects.count(),1)
        self.grant('view_receivable')
        self.assertEqual(self.post(f'receivables/{self.receivable.pk}/receive/',body).status_code,403)
        self.assertEqual(FinancialEntry.objects.count(),1)

    def test_receipt_permission_does_not_grant_listing_or_account_balances(self):
        self.grant('receive_receivable')
        self.assertEqual(self.client.get(self.url('receivables/')).status_code,403)
        r=self.client.get(self.url('sales/payment-options/'));self.assertEqual(r.status_code,200)
        self.assertFalse(r.data['can_view_balances']);self.assertNotIn('balance',r.data['accounts'][0])
        self.grant('receive_receivable','view_financialaccount')
        r=self.client.get(self.url('sales/payment-options/'));self.assertTrue(r.data['can_view_balances']);self.assertIn('balance',r.data['accounts'][0])

    def test_view_receipts_does_not_grant_receive(self):
        self.grant('view_receivable')
        r=self.client.get(self.url('receivables/'));self.assertEqual(r.status_code,200)
        self.assertFalse(r.data['results'][0]['can_receive'])
        self.assertEqual(self.post(f'receivables/{self.receivable.pk}/receive/',self.receipt()).status_code,403)

    def test_receive_cash_automatically_posts_without_manual_move_permission(self):
        self.grant('receive_receivable')
        body=self.receipt(account_id=self.cash.pk,method_id=self.money.pk)
        self.assertEqual(self.post(f'receivables/{self.receivable.pk}/receive/',body).status_code,200)
        self.assertEqual(CashPosting.objects.get().amount,Decimal('10'))
        self.assertEqual(self.post(f'cash/{self.session.pk}/postings/',self.move()).status_code,403)

    def test_closed_cash_blocks_receipt_without_partial_writes(self):
        self.grant('close_cash','receive_receivable')
        self.assertEqual(self.post(f'cash/{self.session.pk}/close/',self.close()).status_code,200)
        body=self.receipt(account_id=self.cash.pk,method_id=self.money.pk)
        self.assertEqual(self.post(f'receivables/{self.receivable.pk}/receive/',body).status_code,400)
        self.assertFalse(FinancialEntry.objects.exists());self.assertFalse(CashPosting.objects.exists())

    def test_checkout_cannot_confirm_receipt_without_permission(self):
        self.grant('add_sale','finalize_sale')
        body={'request_id':str(uuid.uuid4()),'action':'complete','items':[{'product_id':self.product.pk,'quantity':'1','unit_price':'50'}],
            'payments':[{'method_id':self.pix.pk,'account_id':self.bank.pk,'amount':'50','first_due_date':str(date.today()),'confirmed':True}]}
        before=Sale.objects.count();stock=StockMovement.objects.count()
        self.assertEqual(self.post('sales/checkout/',body).status_code,403)
        self.assertEqual(Sale.objects.count(),before);self.assertEqual(StockMovement.objects.count(),stock)
        self.grant('add_sale','finalize_sale','receive_receivable')
        self.assertEqual(self.post('sales/checkout/',body).status_code,200)
        self.grant('add_sale','finalize_sale')
        self.assertEqual(self.post('sales/checkout/',body).status_code,403)
        self.assertEqual(FinancialEntry.objects.count(),1)

    def test_saved_confirmed_plan_cannot_bypass_receipt_permission(self):
        self.grant('finalize_sale')
        sale=Sale.objects.create(store=self.store,created_by=self.user)
        SaleItem.objects.create(sale=sale,product=self.product,quantity=1)
        SalePayment.objects.create(sale=sale,account=self.bank,method=self.pix,amount=50,first_due_date=date.today(),confirmed=True)
        self.assertEqual(self.post(f'sales/{sale.pk}/finalize/',{}).status_code,403)
        sale.refresh_from_db();self.assertEqual(sale.status,'draft');self.assertFalse(FinancialEntry.objects.exists())

    def test_group_revocation_is_immediate(self):
        group=Group.objects.create(name='Operação de caixa')
        group.permissions.add(Permission.objects.get(codename='move_cash'));self.user.groups.add(group)
        body=self.move();self.assertEqual(self.post(f'cash/{self.session.pk}/postings/',body).status_code,200)
        group.permissions.clear();self.assertEqual(self.post(f'cash/{self.session.pk}/postings/',body).status_code,403)

    def test_scoping_and_inactive_user_link_store_company(self):
        self.grant('view_cashsession','move_cash','view_receivable','receive_receivable')
        self.assertEqual(self.client.get(self.url('cash/',self.other)).status_code,400)
        for obj in [self.user,self.link,self.store,self.company]:
            obj.is_active=False;obj.save(update_fields=['is_active'])
            self.assertIn(self.post(f'cash/{self.session.pk}/postings/',self.move()).status_code,[400,403])
            self.assertIn(self.post(f'receivables/{self.receivable.pk}/receive/',self.receipt()).status_code,[400,403])
            obj.is_active=True;obj.save(update_fields=['is_active'])

    def test_access_is_own_uncached_and_csrf_is_required(self):
        r=self.client.get(self.url('finance-access/'));self.assertEqual(r.status_code,200);self.assertIn('no-store',r['Cache-Control'])
        self.grant('move_cash','receive_receivable')
        browser=APIClient(enforce_csrf_checks=True);browser.force_login(self.user)
        self.assertEqual(browser.post(self.url(f'cash/{self.session.pk}/postings/'),self.move(),format='json').status_code,403)
        self.assertEqual(browser.post(self.url(f'receivables/{self.receivable.pk}/receive/'),self.receipt(),format='json').status_code,403)
        self.assertFalse(CashPosting.objects.exists());self.assertFalse(FinancialEntry.objects.exists())

    def test_superuser_and_anonymous(self):
        self.client.force_authenticate(None);self.assertEqual(self.client.get(self.url('finance-access/')).status_code,403)
        self.user.is_superuser=True;self.user.save(update_fields=['is_superuser']);self.client.force_authenticate(self.user)
        self.assertEqual(self.post(f'cash/{self.session.pk}/postings/',self.move()).status_code,200)
        self.assertEqual(self.post(f'receivables/{self.receivable.pk}/receive/',self.receipt()).status_code,200)

    def test_admin_financial_history_is_global_superuser_only_and_readonly(self):
        from django.contrib import admin
        from django.test import RequestFactory
        self.user.is_staff=True;self.user.save(update_fields=['is_staff'])
        self.grant('view_cashsession','view_receivable','view_financialaccount')
        for model in [CashSession,CashPosting,Receivable,FinancialEntry,FinancialAccount]:
            request=RequestFactory().get('/admin/');request.user=self.user
            handler=admin.site._registry[model]
            self.assertFalse(handler.has_view_permission(request));self.assertEqual(handler.get_queryset(request).count(),0)
        self.user.is_superuser=True;self.user.save(update_fields=['is_superuser'])
        for model in [CashSession,CashPosting,Receivable,FinancialEntry]:
            request=RequestFactory().get('/admin/');request.user=self.user
            handler=admin.site._registry[model]
            self.assertTrue(handler.has_view_permission(request));self.assertFalse(handler.has_add_permission(request));self.assertFalse(handler.has_change_permission(request));self.assertFalse(handler.has_delete_permission(request))


from purchases import test_payables as payable_fixtures


class SupplierCashPermissionTests(TestCase):
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

    def test_cash_payment_and_reversal_replays_recheck_cash_permission(self):
        from purchases.models import PayablePayment
        plan=self.plan();installment=plan['installments'][0]['id']
        open_cash(user=self.user,store=self.store,account_id=self.cash.pk,amount=Decimal('100'),note='',request_id=uuid.uuid4())
        payload=self.pay_data(account_id=self.cash.pk,method_id=self.methods['cash'].pk)
        permission=Permission.objects.get(codename='move_cash');self.user.user_permissions.remove(permission)
        self.pay(installment,payload,expected=403);self.assertEqual(PayablePayment.objects.count(),0)
        self.user.user_permissions.add(permission)
        self.pay(installment,payload);payment=PayablePayment.objects.get()
        reversal={'request_id':str(uuid.uuid4()),'reason':'Correção'}
        self.reverse(payment.pk,reversal)
        self.user.user_permissions.remove(permission)
        self.pay(installment,payload,expected=403);self.reverse(payment.pk,reversal,expected=403)
        self.assertEqual(PayablePayment.objects.count(),2);self.assertEqual(CashPosting.objects.count(),2)

    def test_bank_payment_does_not_require_manual_cash_rights(self):
        self.user.user_permissions.remove(Permission.objects.get(codename='move_cash'))
        plan=self.plan();self.pay(plan['installments'][0]['id'])
        self.assertFalse(CashPosting.objects.exists())

    def test_supplier_options_hide_cash_and_balances_without_rights(self):
        self.user.user_permissions.remove(Permission.objects.get(codename='move_cash'))
        response=self.client.get(self.payable_url('options/'))
        self.assertEqual(response.status_code,200)
        self.assertFalse(response.data['can_cash']);self.assertFalse(response.data['can_view_balances'])
        self.assertFalse(any(m['kind']=='cash' for m in response.data['methods']))
        self.assertTrue(all('balance' not in a for a in response.data['accounts']))
