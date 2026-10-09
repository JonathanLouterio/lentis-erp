from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from organizations.models import Company, Product, StockMovement, Store
from organizations.stock_services import register_stock_movement
from .models import FinancialEntry, Sale


class NegativeStockTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(username='negative_admin', password='test-only-password', email='test@example.com')
        self.store = Store.objects.create(company=Company.objects.create(name='Estoque negativo'), code='NEG', name='Matriz')
        self.product = Product.objects.create(store=self.store, internal_code='NEG001', name='Produto sem estoque', sale_price=Decimal('100'))
        self.client = APIClient(); self.client.force_authenticate(self.user)
        from django.core.management import call_command
        from io import StringIO
        call_command('setup_payments', store_id=self.store.pk, stdout=StringIO())
        from .models import PaymentMethod, FinancialAccount
        self.method = PaymentMethod.objects.get(store=self.store, kind='pix')
        self.account = FinancialAccount.objects.get(store=self.store, code='bank')

    def payload(self):
        return {'request_id':str(uuid4()), 'action':'complete', 'customer_id':None, 'discount_amount':'0',
                'items':[{'product_id':self.product.pk, 'quantity':'1', 'unit_price':'100', 'discount_amount':'0'}],
                'payments':[{'method_id':self.method.pk,'account_id':self.account.pk,'amount':'100',
                    'confirmed':True,'installment_count':1,'first_due_date':'2026-10-09'}]}

    def sale(self, payload=None, expected=200):
        response = self.client.post(f'/api/me/sales/checkout/?store_id={self.store.pk}',payload or self.payload(),format='json')
        self.assertEqual(response.status_code,expected,response.data)
        return response

    def stock(self, kind, quantity):
        return register_stock_movement(user=self.user,store_id=self.store.pk,product_id=self.product.pk,
            movement_type=kind,quantity=quantity,reason='Teste do saldo negativo')

    def test_sale_without_stock_is_completed_with_warning_and_real_balance(self):
        self.assertTrue(self.store.allow_negative_stock)
        result=self.sale()
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,Decimal('-1'))
        self.assertEqual(result.data['status'],'completed')
        self.assertEqual(result.data['stock_warnings'][0]['balance_after'],'-1.000')
        self.assertEqual(StockMovement.objects.get().balance_before,Decimal('0'))
        self.assertEqual(StockMovement.objects.get().balance_after,Decimal('-1'))
        self.assertEqual(FinancialEntry.objects.count(),1)

    def test_repeat_does_not_duplicate_negative_stock_or_receipt(self):
        payload=self.payload();self.sale(payload);self.sale(payload)
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,Decimal('-1'))
        self.assertEqual((Sale.objects.count(),StockMovement.objects.count(),FinancialEntry.objects.count()),(1,1,1))

    def test_policy_can_block_sale_and_roll_back_everything(self):
        self.store.allow_negative_stock=False;self.store.save()
        self.sale(expected=400)
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,Decimal('0'))
        self.assertFalse(Sale.objects.exists());self.assertFalse(StockMovement.objects.exists());self.assertFalse(FinancialEntry.objects.exists())

    def test_negative_stock_is_replenished_without_resetting_balance(self):
        self.sale();self.stock('entry','0.250')
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,Decimal('-0.750'))
        self.stock('entry','2');self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,Decimal('1.250'))

    def test_replenishment_and_cancellation_work_after_policy_is_disabled(self):
        result=self.sale();self.store.allow_negative_stock=False;self.store.save()
        self.stock('entry','0.250')
        response=self.client.post(f'/api/me/sales/{result.data["id"]}/cancel/?store_id={self.store.pk}',{'reason':'Teste cancelado'},format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,Decimal('0.250'))
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance,Decimal('0'))

    def test_negative_sale_warning_is_historical_after_replenishment(self):
        result=self.sale();self.stock('entry','5')
        response=self.client.get(f'/api/me/sales/{result.data["id"]}/?store_id={self.store.pk}')
        self.assertEqual(response.data['stock_warnings'][0]['balance_after'],'-1.000')
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,Decimal('4'))

    def test_manual_exit_respects_unit_policy(self):
        self.stock('exit','2')
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,Decimal('-2'))
        self.store.allow_negative_stock=False;self.store.save()
        with self.assertRaises(ValidationError):self.stock('exit','1')
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,Decimal('-2'))

    def test_physical_count_can_regularize_negative_balance_to_zero(self):
        self.sale();self.stock('adjustment','0')
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,Decimal('0'))
        with self.assertRaises(ValidationError):self.stock('adjustment','-1')

    def test_negative_price_and_minimum_stock_remain_invalid(self):
        self.product.stock_quantity=Decimal('-1');self.product.full_clean()
        for field in ['cost_price','sale_price','minimum_stock']:
            original=getattr(self.product,field);setattr(self.product,field,Decimal('-1'))
            with self.assertRaises(ValidationError):self.product.full_clean()
            setattr(self.product,field,original)
        with self.assertRaises(IntegrityError),transaction.atomic():
            Product.objects.filter(pk=self.product.pk).update(sale_price=-1)

    def test_edit_product_preserves_negative_stock(self):
        self.sale()
        response=self.client.patch(f'/api/me/products/{self.product.pk}/?store_id={self.store.pk}',{'name':'Produto revisado'},format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,Decimal('-1'))

    def test_signed_balance_limit_and_large_quantity_change_are_handled(self):
        self.product.stock_quantity=Decimal('-999999999.999');self.product.save()
        with self.assertRaises(ValidationError):self.stock('exit','0.001')
        self.stock('adjustment','999999999.999')
        response=self.client.get(f'/api/me/stock-movements/?store_id={self.store.pk}')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data[0]['quantity_change'],'1999999999.998')

    def test_policy_is_returned_by_api(self):
        url=f'/api/me/sales/payment-options/?store_id={self.store.pk}'
        self.assertTrue(self.client.get(url).data['allow_negative_stock'])
        self.store.allow_negative_stock=False;self.store.save()
        self.assertFalse(self.client.get(url).data['allow_negative_stock'])

    def test_warning_lists_each_negative_product_only_once(self):
        other = Product.objects.create(store=self.store, internal_code='NEG002', name='Outro sem estoque', sale_price=Decimal('100'))
        payload = self.payload()
        payload['items'].append({'product_id':other.pk, 'quantity':'1', 'unit_price':'100', 'discount_amount':'0'})
        payload['payments'][0]['amount'] = '200'
        result = self.sale(payload)
        self.assertEqual(len(result.data['stock_warnings']), 2)
        self.assertEqual({item['product'] for item in result.data['stock_warnings']}, {self.product.pk,other.pk})

    def test_warning_does_not_include_product_with_positive_balance(self):
        other = Product.objects.create(store=self.store, internal_code='POS001', name='Com estoque', stock_quantity=Decimal('5'), sale_price=Decimal('100'))
        payload = self.payload()
        payload['items'].append({'product_id':other.pk, 'quantity':'1', 'unit_price':'100', 'discount_amount':'0'})
        payload['payments'][0]['amount'] = '200'
        result = self.sale(payload)
        self.assertEqual(len(result.data['stock_warnings']), 1)
        self.assertEqual(result.data['stock_warnings'][0]['product'], self.product.pk)
