from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from . import test_payments as fixtures
from .models import Quote, QuoteItem, QuoteEvent, Sale, FinancialEntry, Receivable
from organizations.models import StockMovement


class QuoteAPITests(TestCase):
    def setUp(self):
        fixtures.PaymentCheckoutTests.setUp(self)
        self.base = '/api/me/quotes/'

    def payload(self, **overrides):
        data = {'request_id': str(uuid4()), 'customer_id': self.customer.pk,
                'valid_until': str(timezone.localdate() + timedelta(days=15)), 'notes': 'Proposta de teste',
                'discount_amount': '10', 'items': [{'product_id': self.product.pk,
                'quantity': '2', 'unit_price': '650', 'discount_amount': '20'}]}
        data.update(overrides)
        return data

    def write(self, data=None, quote=None, expected=200):
        path = f'{self.base}{quote["id"]}/' if quote else self.base
        method = self.client.put if quote else self.client.post
        response = method(f'{path}?store_id={self.store.pk}', data or self.payload(), format='json')
        self.assertEqual(response.status_code, expected, response.data)
        return response.data

    def action(self, quote, action, *, expected=200, **overrides):
        data = {'request_id': str(uuid4()), 'expected_version': quote['version']}
        data.update(overrides)
        response = self.client.post(f'{self.base}{quote["id"]}/{action}/?store_id={self.store.pk}', data, format='json')
        self.assertEqual(response.status_code, expected, response.data)
        return response.data

    def accepted(self):
        return self.action(self.action(self.write(), 'send'), 'accept')

    def assert_no_effects(self):
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal('10'))
        self.assertFalse(StockMovement.objects.exists())
        self.assertFalse(FinancialEntry.objects.exists())
        self.assertFalse(Receivable.objects.exists())

    def test_lifecycle_preserves_prices_and_has_no_stock_or_financial_effects(self):
        quote = self.accepted()
        self.product.sale_price = Decimal('800'); self.product.save()
        result = self.action(quote, 'convert')
        sale = Sale.objects.get(pk=result['sale'])
        self.assertEqual(sale.status, 'draft')
        self.assertEqual(sale.total, Decimal('1270'))
        self.assertEqual(sale.items.get().unit_price, Decimal('650'))
        self.assertEqual(sale.items.get().reference_price, Decimal('800'))
        self.assertEqual(sale.customer, self.customer)
        self.assertEqual(list(QuoteEvent.objects.values_list('action', flat=True)), ['created','send','accept','convert'])
        self.assert_no_effects()

    def test_conversion_retries_create_only_one_sale(self):
        quote = self.accepted()
        request_id = str(uuid4())
        first = self.action(quote, 'convert', request_id=request_id)
        second = self.action(quote, 'convert', request_id=request_id)
        third = self.action(quote, 'convert')
        self.assertEqual(first['sale'], second['sale']); self.assertEqual(first['sale'], third['sale'])
        self.assertEqual(Sale.objects.count(), 1)
        self.assertEqual(QuoteEvent.objects.filter(action='convert').count(), 1)
        self.assert_no_effects()

    def test_creation_retry_and_changed_payload(self):
        data = self.payload()
        first = self.write(data); second = self.write(data)
        self.assertEqual(first['id'], second['id']); self.assertEqual(Quote.objects.count(), 1)
        data['notes'] = 'Outro'; self.write(data, expected=400)

    def test_edit_accepted_quote_resets_acceptance_and_preserves_version(self):
        quote = self.accepted()
        edited = self.write(self.payload(expected_version=quote['version']), quote)
        self.assertEqual(edited['status'], 'draft')
        self.assertEqual(edited['version'], quote['version'] + 1)
        self.action(edited, 'convert', expected=400)
        self.assertFalse(Sale.objects.exists())

    def test_stale_edit_changes_nothing(self):
        quote = self.write()
        self.action(quote, 'send')
        self.write(self.payload(expected_version=quote['version']), quote, expected=400)
        self.assertEqual(Quote.objects.get().status, 'sent')

    def test_expired_proposal_requires_revision(self):
        quote = self.write(self.payload(valid_until=str(timezone.localdate() - timedelta(days=2))))
        self.action(quote, 'send', expected=400)
        edited = self.write(self.payload(expected_version=quote['version']), quote)
        self.assertEqual(self.action(edited, 'send')['status'], 'sent')

    def test_empty_draft_cannot_be_prepared(self):
        quote = self.write(self.payload(items=[], discount_amount='0'))
        self.action(quote, 'send', expected=400)

    def test_duplicate_products_and_excessive_discount_are_rejected(self):
        data = self.payload(); data['items'] *= 2
        self.write(data, expected=400)
        self.write(self.payload(discount_amount='1500'), expected=400)
        self.assertFalse(Quote.objects.exists())

    def test_recusal_requires_reason_and_makes_proposal_read_only(self):
        quote = self.write()
        self.action(quote, 'reject', expected=400)
        rejected = self.action(quote, 'reject', reason='Cliente desistiu')
        self.write(self.payload(expected_version=rejected['version']), rejected, expected=400)
        self.action(rejected, 'convert', expected=400)
        self.assertEqual(Quote.objects.get().status, 'rejected')
        self.assert_no_effects()

    def test_inactive_product_blocks_conversion_without_partial_sale(self):
        quote = self.accepted()
        self.product.is_active = False; self.product.save()
        self.action(quote, 'convert', expected=400)
        self.assertFalse(Sale.objects.exists())
        self.assertEqual(Quote.objects.get().status, 'accepted')

    def test_conversion_failure_rolls_back_sale_and_history(self):
        quote = self.accepted()
        with patch('sales.quote_services.SaleItem.objects.create', side_effect=RuntimeError('Falha simulada')):
            with self.assertRaises(RuntimeError): self.action(quote, 'convert')
        self.assertFalse(Sale.objects.exists())
        self.assertEqual(Quote.objects.get().status, 'accepted')
        self.assertFalse(QuoteEvent.objects.filter(action='convert').exists())

    def test_other_store_and_revoked_membership_are_denied(self):
        quote = self.write()
        response = self.client.get(f'{self.base}{quote["id"]}/?store_id={self.other.pk}')
        self.assertIn(response.status_code, [400,403,404])
        from accounts.models import StoreMembership
        StoreMembership.objects.filter(user=self.user).update(is_active=False)
        response = self.client.get(f'{self.base}?store_id={self.store.pk}')
        self.assertIn(response.status_code, [400,403])

    def test_anonymous_and_missing_csrf_cannot_write(self):
        client = APIClient(enforce_csrf_checks=True)
        path = f'{self.base}?store_id={self.store.pk}'
        self.assertEqual(client.post(path, self.payload(), format='json').status_code, 403)
        client.force_login(self.user)
        self.assertEqual(client.post(path, self.payload(), format='json').status_code, 403)
        self.assertFalse(Quote.objects.exists())

    def test_optional_price_uses_current_catalog_and_zero_stock_is_allowed(self):
        self.product.stock_quantity = 0; self.product.save()
        quote = self.write(self.payload(items=[{'product_id': self.product.pk, 'quantity': '1'}], discount_amount='0'))
        self.assertEqual(quote['total'], '700.00')
        quote = self.action(self.action(quote, 'send'), 'accept')
        self.action(quote, 'convert')
        self.product.refresh_from_db(); self.assertEqual(self.product.stock_quantity, 0)
        self.assertFalse(StockMovement.objects.exists())

    def test_converted_quote_cannot_be_deleted_or_changed(self):
        quote = self.action(self.accepted(), 'convert')
        self.write(self.payload(expected_version=quote['version']), quote, expected=400)
        response = self.client.delete(f'{self.base}{quote["id"]}/?store_id={self.store.pk}')
        self.assertEqual(response.status_code, 405)
        self.assertEqual(QuoteItem.objects.count(), 1)

    def test_customer_and_product_must_belong_to_selected_store(self):
        from organizations.models import Customer, Product
        customer = Customer.objects.create(store=self.other, name='Outra unidade')
        product = Product.objects.create(store=self.other, internal_code='OTHER', name='Outro produto', sale_price=10)
        self.write(self.payload(customer_id=customer.pk), expected=400)
        self.write(self.payload(items=[{'product_id': product.pk, 'quantity':'1'}]), expected=400)
        self.assertFalse(Quote.objects.exists())

    def test_client_cannot_forge_status_author_sale_or_totals(self):
        quote = self.write(self.payload(status='converted', created_by=self.admin.pk, sale=999, total='1', store=self.other.pk))
        record = Quote.objects.get(pk=quote['id'])
        self.assertEqual(record.status, 'draft'); self.assertEqual(record.created_by, self.user)
        self.assertEqual(record.store, self.store); self.assertIsNone(record.sale_id)
        self.assertEqual(quote['total'], '1270.00')


from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import TransactionTestCase, skipUnlessDBFeature
from .quote_services import operate_quote


class QuoteConcurrencyTests(TransactionTestCase):
    setUp = QuoteAPITests.setUp
    payload = QuoteAPITests.payload
    write = QuoteAPITests.write
    action = QuoteAPITests.action
    accepted = QuoteAPITests.accepted

    @skipUnlessDBFeature('has_select_for_update')
    def test_two_operators_convert_same_quote_to_one_sale(self):
        quote = self.accepted()
        barrier = Barrier(2)
        def convert(user_id):
            close_old_connections()
            try:
                user = get_user_model().objects.get(pk=user_id)
                barrier.wait(timeout=10)
                result = operate_quote(user=user, store=self.store, quote_id=quote['id'], action='convert',
                    request_id=uuid4(), digest=str(user_id), validated_values=lambda: {'expected_version':quote['version']})
                return result.sale_id
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            sales = list(pool.map(convert, [self.user.pk, self.admin.pk]))
        self.assertEqual(sales[0], sales[1]); self.assertEqual(Sale.objects.count(), 1)
        self.assertEqual(QuoteEvent.objects.filter(action='convert').count(), 1)
