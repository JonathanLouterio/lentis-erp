from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, connections
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature

from accounts.models import StoreMembership
from organizations.models import Company, Product, StockMovement, Store
from organizations.stock_services import register_stock_movement

from .models import Sale, SaleEvent, SaleItem, SaleStockMovement
from .services import cancel_sale, finalize_sale


class SaleServiceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(username="sale_service_admin", email="sales@example.com", password="test")
        company = Company.objects.create(name="Empresa serviços")
        self.store = Store.objects.create(company=company, code="01", name="Matriz", allow_negative_stock=False)
        self.product = Product.objects.create(store=self.store, internal_code="S001", name="Produto teste", sale_price=Decimal("100"), stock_quantity=Decimal("10"))
        self.sale = Sale.objects.create(store=self.store, created_by=self.user)
        self.item = SaleItem.objects.create(sale=self.sale, product=self.product, quantity=Decimal("2"))

    def finish(self):
        return finalize_sale(user=self.user, sale_id=self.sale.pk)

    def cancel(self, reason="Pedido cancelado"):
        return cancel_sale(user=self.user, sale_id=self.sale.pk, reason=reason)

    def assert_balance(self, expected):
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal(expected))

    def test_finalization_updates_stock_and_records_author_and_links(self):
        sale = self.finish()
        self.assertEqual(sale.status, Sale.Status.COMPLETED)
        self.assertIsNotNone(sale.completed_at)
        self.assert_balance("8")
        event = SaleEvent.objects.get(sale=sale)
        self.assertEqual(event.created_by, self.user)
        link = SaleStockMovement.objects.get(event=event)
        self.assertEqual(link.item_id, self.item.pk)
        self.assertEqual(link.movement.movement_type, "exit")
        self.assertEqual(link.movement.quantity, Decimal("2"))

    def test_sale_with_multiple_products(self):
        second = Product.objects.create(store=self.store, internal_code="S002", name="Segundo", stock_quantity=Decimal("5"), sale_price=Decimal("50"))
        SaleItem.objects.create(sale=self.sale, product=second, quantity=Decimal("3"))
        sale = self.finish()
        self.assertEqual(sale.total, Decimal("350.00"))
        self.assert_balance("8")
        second.refresh_from_db()
        self.assertEqual(second.stock_quantity, Decimal("2"))
        self.assertEqual(SaleStockMovement.objects.count(), 2)

    def test_empty_sale_cannot_be_finalized(self):
        self.item.delete()
        with self.assertRaises(ValidationError):
            self.finish()
        self.assertFalse(SaleEvent.objects.exists())

    def test_insufficient_stock_in_any_item_changes_nothing(self):
        second = Product.objects.create(store=self.store, internal_code="S002", name="Sem saldo", stock_quantity=Decimal("1"))
        SaleItem.objects.create(sale=self.sale, product=second, quantity=Decimal("2"))
        with self.assertRaises(ValidationError):
            self.finish()
        self.assert_balance("10")
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.Status.DRAFT)
        self.assertFalse(SaleEvent.objects.exists())
        self.assertFalse(StockMovement.objects.exists())

    def test_failure_after_stock_write_rolls_back_everything(self):
        with patch.object(SaleStockMovement, "save", side_effect=RuntimeError("Test failure")):
            with self.assertRaises(RuntimeError):
                self.finish()
        self.assert_balance("10")
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.Status.DRAFT)
        self.assertFalse(SaleEvent.objects.exists())
        self.assertFalse(StockMovement.objects.exists())

    def test_inactive_product_prevents_finalization(self):
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])
        with self.assertRaises(ValidationError):
            self.finish()
        self.assert_balance("10")

    def test_repeated_finalization_does_not_duplicate_stock_exit(self):
        self.finish()
        self.finish()
        self.assert_balance("8")
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertEqual(SaleEvent.objects.count(), 1)

    def test_cancellation_returns_stock_and_records_reason(self):
        self.finish()
        sale = self.cancel()
        self.assertEqual(sale.status, Sale.Status.CANCELLED)
        self.assertEqual(sale.cancellation_reason, "Pedido cancelado")
        self.assertIsNotNone(sale.cancelled_at)
        self.assert_balance("10")
        event = SaleEvent.objects.get(sale=sale, event_type="cancelled")
        self.assertEqual(event.reason, "Pedido cancelado")
        self.assertEqual(event.created_by, self.user)
        self.assertEqual(event.stock_movements.get().movement.movement_type, "entry")

    def test_repeated_cancellation_does_not_duplicate_return_or_change_reason(self):
        self.finish()
        self.cancel()
        sale = self.cancel("Outro motivo")
        self.assert_balance("10")
        self.assertEqual(StockMovement.objects.count(), 2)
        self.assertEqual(SaleEvent.objects.count(), 2)
        self.assertEqual(sale.cancellation_reason, "Pedido cancelado")

    def test_cancellation_restores_stock_of_inactive_product(self):
        self.finish()
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])
        self.cancel()
        self.assert_balance("10")
        self.assertFalse(self.product.is_active)

    def test_cancelling_draft_does_not_change_stock(self):
        sale = self.cancel()
        self.assertEqual(sale.status, Sale.Status.CANCELLED)
        self.assertIsNone(sale.completed_at)
        self.assert_balance("10")
        self.assertFalse(StockMovement.objects.exists())
        self.assertEqual(SaleEvent.objects.count(), 1)

    def test_cancelled_sale_cannot_be_finalized_again(self):
        self.cancel()
        with self.assertRaises(ValidationError):
            self.finish()
        self.assert_balance("10")

    def test_cancellation_requires_valid_reason(self):
        for reason in ("", "   ", None, "x" * 256):
            with self.subTest(reason=reason), self.assertRaises(ValidationError):
                self.cancel(reason)
        self.assertFalse(SaleEvent.objects.exists())

    def test_anonymous_unlinked_or_inactive_user_is_denied(self):
        unlinked = get_user_model().objects.create_user(username="sale_unlinked")
        inactive = get_user_model().objects.create_superuser(username="sale_inactive", email="inactive@example.com", password="test", is_active=False)
        for user in (AnonymousUser(), unlinked, inactive):
            with self.subTest(user=user), self.assertRaises(PermissionDenied):
                finalize_sale(user=user, sale_id=self.sale.pk)
        self.assert_balance("10")

    def test_linked_seller_can_finalize_but_not_cancel_completed_sale(self):
        seller = get_user_model().objects.create_user(username="sale_seller")
        StoreMembership.objects.create(user=seller, store=self.store, role=StoreMembership.Role.SELLER)
        finalize_sale(user=seller, sale_id=self.sale.pk)
        self.assertEqual(SaleEvent.objects.get().created_by, seller)
        with self.assertRaises(PermissionDenied):
            cancel_sale(user=seller, sale_id=self.sale.pk, reason="Teste")
        self.assert_balance("8")

    def test_staff_cannot_bypass_store_membership(self):
        self.finish()
        staff = get_user_model().objects.create_user(username="sale_staff", is_staff=True)
        with self.assertRaises(PermissionDenied):
            cancel_sale(user=staff, sale_id=self.sale.pk, reason="Teste")
        self.assert_balance("8")

    def test_cancellation_failure_rolls_back_return_and_event(self):
        self.finish()
        with patch.object(Sale, "save", side_effect=RuntimeError("Test failure")):
            with self.assertRaises(RuntimeError):
                self.cancel()
        self.assert_balance("8")
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.Status.COMPLETED)
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertFalse(SaleEvent.objects.filter(event_type="cancelled").exists())

    def test_stock_overflow_prevents_cancellation_without_partial_changes(self):
        self.finish()
        register_stock_movement(user=self.user, store_id=self.store.pk, product_id=self.product.pk, movement_type="entry", quantity="999999991", reason="Saldo para teste de limite")
        with self.assertRaises(ValidationError):
            self.cancel()
        self.assert_balance("999999999")
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.Status.COMPLETED)
        self.assertEqual(StockMovement.objects.count(), 2)
        self.assertFalse(SaleEvent.objects.filter(event_type="cancelled").exists())

    def test_event_and_stock_link_are_immutable(self):
        self.finish()
        event = SaleEvent.objects.get()
        link = SaleStockMovement.objects.get()
        for operation in (event.save, event.delete, link.save, link.delete):
            with self.assertRaises(ValidationError):
                operation()

    def test_revocation_blocks_even_a_repeated_request(self):
        seller = get_user_model().objects.create_user(username="sale_revoked")
        membership = StoreMembership.objects.create(user=seller, store=self.store, role=StoreMembership.Role.SELLER)
        finalize_sale(user=seller, sale_id=self.sale.pk)
        membership.is_active = False
        membership.save(update_fields=["is_active"])
        with self.assertRaises(PermissionDenied):
            finalize_sale(user=seller, sale_id=self.sale.pk)
        self.assert_balance("8")


@skipUnlessDBFeature("has_select_for_update")
class SaleConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(username="sale_concurrent", email="concurrent@example.com", password="test")
        self.store = Store.objects.create(company=Company.objects.create(name="Empresa concorrência"), code="01", name="Matriz", allow_negative_stock=False)
        self.product = Product.objects.create(store=self.store, internal_code="C001", name="Produto", stock_quantity=Decimal("10"), sale_price=Decimal("100"))

    def new_sale(self, quantity="2"):
        sale = Sale.objects.create(store=self.store, created_by=self.user)
        SaleItem.objects.create(sale=sale, product=self.product, quantity=Decimal(quantity))
        return sale

    def concurrently(self, sale_ids, operation):
        barrier = Barrier(2)

        def worker(sale_id):
            try:
                if connection.vendor == "postgresql":
                    with connection.cursor() as cursor:
                        cursor.execute("SET lock_timeout = '5s'")
                barrier.wait(timeout=10)
                try:
                    operation(sale_id)
                    return "ok"
                except ValidationError:
                    return "rejected"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, sale_id) for sale_id in sale_ids]
            return [future.result(timeout=20) for future in futures]

    def test_simultaneous_finalization_of_same_sale_debits_once(self):
        sale = self.new_sale()
        results = self.concurrently([sale.pk, sale.pk], lambda pk: finalize_sale(user=self.user, sale_id=pk))
        self.assertEqual(results, ["ok", "ok"])
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("8"))
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_simultaneous_sales_cannot_oversell(self):
        Product.objects.filter(pk=self.product.pk).update(stock_quantity=Decimal("6"))
        first, second = self.new_sale("4"), self.new_sale("4")
        results = self.concurrently([first.pk, second.pk], lambda pk: finalize_sale(user=self.user, sale_id=pk))
        self.assertEqual(sorted(results), ["ok", "rejected"])
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("2"))
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_simultaneous_cancellation_returns_stock_once(self):
        sale = self.new_sale()
        finalize_sale(user=self.user, sale_id=sale.pk)
        results = self.concurrently([sale.pk, sale.pk], lambda pk: cancel_sale(user=self.user, sale_id=pk, reason="Teste concorrência"))
        self.assertEqual(results, ["ok", "ok"])
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("10"))
        self.assertEqual(StockMovement.objects.count(), 2)
