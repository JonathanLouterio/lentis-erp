from decimal import Decimal
from uuid import uuid4

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import StoreMembership
from organizations.models import Company, Customer, Product, StockMovement, Store
from .models import DiscountAuthorization, DiscountPolicy, FinancialAccount, FinancialEntry, PaymentMethod, Sale, SaleItem


class DiscountRulesTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.seller = User.objects.create_user(username='discount_seller',password='test-only-password')
        self.reviewer = User.objects.create_superuser(username='discount_reviewer',email='test@example.com',password='test-only-password')
        self.staff = User.objects.create_user(username='discount_staff',is_staff=True)
        self.store = Store.objects.create(company=Company.objects.create(name='Regras comerciais'),code='DC',name='Matriz')
        for user in [self.seller,self.staff]:StoreMembership.objects.create(user=user,store=self.store,role=StoreMembership.Role.SELLER)
        self.policy = DiscountPolicy.objects.create(store=self.store,role=StoreMembership.Role.SELLER,limit_percentage=Decimal('10'))
        self.product = Product.objects.create(store=self.store,internal_code='DC001',name='Armação',sale_price=Decimal('100'),stock_quantity=Decimal('5'))
        self.account = FinancialAccount.objects.create(store=self.store,code='bank',name='Banco')
        self.method = PaymentMethod.objects.create(store=self.store,code='pix',name='Pix',kind='pix')
        self.client = APIClient();self.client.force_authenticate(self.seller)

    def data(self, action='draft', discount='20'):
        return {'request_id':str(uuid4()),'action':action,'customer_id':None,'notes':'','discount_amount':discount,
            'items':[{'product_id':self.product.pk,'quantity':'1','unit_price':'100','discount_amount':'0'}],
            'payments':[{'method_id':self.method.pk,'account_id':self.account.pk,'amount':str(Decimal('100')-Decimal(discount)),
            'installment_count':1,'first_due_date':'2026-10-09','confirmed':True}]}

    def checkout(self, data=None, expected=200):
        response=self.client.post(f'/api/me/sales/checkout/?store_id={self.store.pk}',data or self.data(),format='json')
        self.assertEqual(response.status_code,expected,response.data)
        return response

    def request(self,sale_id,reason='Negociação com o cliente',expected=200):
        response=self.client.post(f'/api/me/sales/{sale_id}/discount/request/?store_id={self.store.pk}',{'reason':reason},format='json')
        self.assertEqual(response.status_code,expected,response.data)
        return response

    def decide(self,sale_id,request_id,action='approve',reason='Autorizado pelo responsável',expected=200):
        response=self.client.post(f'/api/me/sales/{sale_id}/discount/{request_id}/decision/?store_id={self.store.pk}',{'action':action,'reason':reason},format='json')
        self.assertEqual(response.status_code,expected,response.data)
        return response

    def approved(self):
        data=self.data();result=self.checkout(data)
        sale_id=result.data['id'];self.request(sale_id)
        request=DiscountAuthorization.objects.get(action='request')
        self.client.force_authenticate(self.reviewer);self.decide(sale_id,request.pk)
        self.client.force_authenticate(self.seller)
        data['request_id']=str(uuid4());data['sale_id']=sale_id;data['action']='complete'
        return data, request

    def test_limit_is_returned_per_membership_and_missing_policy_preserves_behavior(self):
        url=f'/api/me/sales/payment-options/?store_id={self.store.pk}'
        self.assertEqual(self.client.get(url).data['discount_limit_percentage'],'10.00')
        self.assertFalse(self.client.get(url).data['can_approve_discount'])
        self.policy.delete()
        self.assertEqual(self.client.get(url).data['discount_limit_percentage'],'100.00')
        self.checkout(self.data('complete'))

    def test_at_limit_is_completed_and_excess_is_atomic(self):
        self.checkout(self.data('complete','10'))
        before=(Sale.objects.count(),StockMovement.objects.count(),FinancialEntry.objects.count())
        self.checkout(self.data('complete','10.01'),400)
        self.assertEqual((Sale.objects.count(),StockMovement.objects.count(),FinancialEntry.objects.count()),before)

    def test_item_and_global_discounts_are_combined(self):
        data=self.data('complete','6');data['items'][0]['discount_amount']='5';data['payments'][0]['amount']='89'
        self.checkout(data,400)
        self.assertFalse(StockMovement.objects.exists())

    def test_reducing_unit_price_also_requires_authorization(self):
        data=self.data('complete','0');data['items'][0]['unit_price']='80';data['payments'][0]['amount']='80'
        self.checkout(data,400)
        data['request_id']=str(uuid4());data['action']='draft';result=self.checkout(data)
        self.assertEqual(result.data['items'][0]['reference_price'],'100.00')
        self.assertEqual(result.data['discount_control']['discount_amount'],'20.00')

    def test_request_is_idempotent_and_does_not_move_stock(self):
        sale=self.checkout().data;self.request(sale['id']);self.request(sale['id'])
        self.assertEqual(DiscountAuthorization.objects.count(),1)
        self.assertFalse(StockMovement.objects.exists());self.assertFalse(FinancialEntry.objects.exists())
        self.assertEqual(self.request(sale['id']).data['discount_control']['state'],'pending')

    def test_approval_allows_same_values_without_duplicate_decisions(self):
        data,request=self.approved()
        self.client.force_authenticate(self.reviewer);self.decide(data['sale_id'],request.pk)
        self.client.force_authenticate(self.seller)
        self.assertEqual(self.checkout(data).data['status'],'completed')
        self.assertEqual(DiscountAuthorization.objects.count(),2)
        self.assertEqual(StockMovement.objects.count(),1);self.assertEqual(FinancialEntry.objects.count(),1)
        self.checkout(data);self.assertEqual(StockMovement.objects.count(),1)

    def test_staff_flag_does_not_grant_approval_but_explicit_permission_does(self):
        sale=self.checkout().data;self.request(sale['id']);request=DiscountAuthorization.objects.get(action='request')
        self.client.force_authenticate(self.staff);self.decide(sale['id'],request.pk,expected=403)
        self.staff.user_permissions.add(Permission.objects.get(codename='approve_discount',content_type__app_label='sales'))
        self.staff=get_user_model().objects.get(pk=self.staff.pk);self.client.force_authenticate(self.staff)
        self.decide(sale['id'],request.pk)

    def test_requester_cannot_approve_own_request(self):
        self.seller.user_permissions.add(Permission.objects.get(codename='approve_discount',content_type__app_label='sales'))
        self.seller=get_user_model().objects.get(pk=self.seller.pk);self.client.force_authenticate(self.seller)
        sale=self.checkout().data;self.request(sale['id']);request=DiscountAuthorization.objects.get(action='request')
        self.decide(sale['id'],request.pk,expected=403)

    def test_changed_values_or_customer_invalidate_authorization(self):
        data,_=self.approved()
        data['discount_amount']='21';data['payments'][0]['amount']='79'
        self.checkout(data,400)
        self.assertFalse(StockMovement.objects.exists())
        data['request_id']=str(uuid4());data['discount_amount']='20';data['payments'][0]['amount']='80'
        data['customer_id']=Customer.objects.create(store=self.store,name='Outro cliente').pk
        self.checkout(data,400)

    def test_changed_policy_invalidates_authorization(self):
        data,_=self.approved();self.policy.limit_percentage=5;self.policy.save()
        self.checkout(data,400);self.assertFalse(StockMovement.objects.exists())

    def test_changed_catalog_price_requires_fresh_review_at_checkout(self):
        data,_=self.approved();self.product.sale_price=Decimal('120');self.product.save()
        self.checkout(data,400)

    def test_benign_notes_do_not_invalidate_approved_amounts(self):
        data,_=self.approved();data['notes']='Entrega amanhã'
        self.checkout(data)

    def test_rejection_blocks_completion_and_allows_new_request(self):
        sale=self.checkout().data;self.request(sale['id']);request=DiscountAuthorization.objects.get(action='request')
        self.client.force_authenticate(self.reviewer);self.decide(sale['id'],request.pk,'reject','Desconto não autorizado')
        self.client.force_authenticate(self.seller)
        data=self.data('complete');data['sale_id']=sale['id'];self.checkout(data,400)
        self.request(sale['id'],'Nova negociação');self.assertEqual(DiscountAuthorization.objects.filter(action='request').count(),2)

    def test_legacy_finalize_cannot_bypass_policy(self):
        sale=self.checkout().data
        response=self.client.post(f'/api/me/sales/{sale["id"]}/finalize/?store_id={self.store.pk}',{},format='json')
        self.assertEqual(response.status_code,400);self.assertFalse(StockMovement.objects.exists())

    def test_forged_approval_or_reference_price_is_ignored(self):
        data=self.data('complete');data['discount_approved']=True;data['discount_control']={'state':'approved'}
        data['items'][0]['reference_price']='0'
        self.checkout(data,400)

    def test_csrf_anonymous_and_cross_unit_access_are_denied(self):
        sale=self.checkout().data
        url=f'/api/me/sales/{sale["id"]}/discount/request/?store_id={self.store.pk}'
        anon=APIClient();self.assertEqual(anon.post(url,{'reason':'Teste'},format='json').status_code,403)
        csrf=APIClient(enforce_csrf_checks=True);csrf.force_login(self.seller)
        self.assertEqual(csrf.post(url,{'reason':'Teste'},format='json').status_code,403)
        other=Store.objects.create(company=self.store.company,code='OUT',name='Outra unidade')
        self.assertEqual(self.client.post(url.replace(f'store_id={self.store.pk}',f'store_id={other.pk}'),{'reason':'Teste'},format='json').status_code,400)
        self.assertEqual(DiscountAuthorization.objects.filter(action="request").count(), 0)

    def test_reasons_and_finished_sale_requests_are_rejected(self):
        sale=self.checkout().data;self.request(sale['id'],' ',400)
        request=self.request(sale['id']).data['discount_control']['request_id']
        self.client.force_authenticate(self.reviewer);self.decide(sale['id'],request,reason=' ',expected=400)
        completed=self.checkout(self.data('complete','0')).data
        self.request(completed['id'],'Teste',400)

    def test_inactive_membership_prevents_approval(self):
        sale=self.checkout().data;self.request(sale['id']);request=DiscountAuthorization.objects.get(action='request')
        self.staff.user_permissions.add(Permission.objects.get(codename='approve_discount',content_type__app_label='sales'))
        StoreMembership.objects.filter(user=self.staff).update(is_active=False)
        self.staff=get_user_model().objects.get(pk=self.staff.pk);self.client.force_authenticate(self.staff)
        self.decide(sale['id'],request.pk,expected=400)
        self.assertFalse(DiscountAuthorization.objects.filter(action='approve').exists())

    def test_approval_records_and_admin_history_are_read_only(self):
        _,request=self.approved()
        request.reason='Alterado'
        with self.assertRaises(ValidationError):request.save()
        with self.assertRaises(ValidationError):request.delete()
        from django.test import RequestFactory
        http=RequestFactory().get('/admin/');http.user=self.reviewer
        model_admin=admin.site._registry[DiscountAuthorization]
        self.assertFalse(model_admin.has_add_permission(http));self.assertFalse(model_admin.has_change_permission(http,request));self.assertFalse(model_admin.has_delete_permission(http,request))

    def test_policy_limits_are_validated_in_model_and_database(self):
        self.policy.limit_percentage=Decimal('-1')
        with self.assertRaises(ValidationError):self.policy.save()
        self.policy.limit_percentage=Decimal('100.01')
        with self.assertRaises(ValidationError):self.policy.save()
        with self.assertRaises(IntegrityError),transaction.atomic():DiscountPolicy.objects.filter(pk=self.policy.pk).update(limit_percentage=101)

    def test_reviewer_sees_request_and_seller_sees_approved_state(self):
        sale=self.checkout().data;self.request(sale['id']);request=DiscountAuthorization.objects.get(action='request')
        self.client.force_authenticate(self.reviewer)
        response=self.client.get(f'/api/me/sales/{sale["id"]}/?store_id={self.store.pk}')
        self.assertTrue(response.data['discount_requests'][0]['can_decide'])
        self.decide(sale['id'],request.pk)
        self.client.force_authenticate(self.seller)
        response=self.client.get(f'/api/me/sales/{sale["id"]}/?store_id={self.store.pk}')
        self.assertEqual(response.data['discount_control']['state'],'approved')
        self.assertTrue(response.data['can_finalize'])

    def test_legacy_item_without_reference_price_keeps_existing_negotiated_price(self):
        sale=Sale.objects.create(store=self.store,created_by=self.seller)
        item=SaleItem.objects.create(sale=sale,product=self.product,unit_price=Decimal('80'))
        SaleItem.objects.filter(pk=item.pk).update(reference_price=None)
        response=self.client.get(f'/api/me/sales/{sale.pk}/?store_id={self.store.pk}')
        self.assertEqual(response.data['discount_control']['discount_percentage'],'0.00')

    def test_admin_policy_and_history_queries_are_scoped_to_accessible_units(self):
        from django.test import RequestFactory
        other = Store.objects.create(company=self.store.company,code='OUT2',name='Filial')
        other_policy = DiscountPolicy.objects.create(store=other,role=StoreMembership.Role.SELLER,limit_percentage=5)
        self.request(self.checkout().data['id'])
        http = RequestFactory().get('/admin/');http.user=self.staff
        policy_admin = admin.site._registry[DiscountPolicy]
        self.assertEqual(list(policy_admin.get_queryset(http).values_list('pk',flat=True)),[self.policy.pk])
        store_field = policy_admin.formfield_for_foreignkey(DiscountPolicy._meta.get_field('store'),http)
        self.assertNotIn(other.pk,list(store_field.queryset.values_list('pk',flat=True)))
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):policy_admin.save_model(http,other_policy,None,True)

    def test_a_different_user_cannot_reuse_someone_elses_authorization(self):
        data,_=self.approved()
        self.client.force_authenticate(self.staff)
        self.checkout(data,400)
        self.assertFalse(StockMovement.objects.exists())

    def test_small_amounts_compare_exactly_before_rounding_percentages(self):
        self.product.sale_price=Decimal('0.05');self.product.save()
        data=self.data('complete','0.01');data['items'][0]['unit_price']='0.05';data['payments'][0]['amount']='0.04'
        self.checkout(data,400)
