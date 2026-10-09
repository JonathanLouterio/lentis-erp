from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from organizations.models import Company, Customer, Product, StockMovement, Store

from .models import Sale, SaleItem


class SaleModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="sale_test")
        company = Company.objects.create(name="Empresa vendas")
        self.store = Store.objects.create(company=company, code="01", name="Matriz")
        self.other_store = Store.objects.create(company=company, code="02", name="Filial")
        self.customer = Customer.objects.create(store=self.store, name="Cliente teste")
        self.product = Product.objects.create(
            store=self.store, internal_code="V001", name="Armação teste",
            sale_price=Decimal("100.00"), stock_quantity=Decimal("10"),
        )
        self.sale = Sale.objects.create(store=self.store, customer=self.customer, created_by=self.user)

    def item(self, **overrides):
        values = {"sale": self.sale, "product": self.product, "quantity": Decimal("2"), "discount_amount": Decimal("10")}
        values.update(overrides)
        return SaleItem.objects.create(**values)

    def mark_completed_for_guard_test(self):
        # Simula apenas um registro histórico para conferir as travas do modelo.
        # A finalização com estoque será coberta pelos testes do serviço depois.
        Sale.objects.filter(pk=self.sale.pk).update(status=Sale.Status.COMPLETED, completed_at=timezone.now())

    def test_draft_can_have_no_customer_and_starts_with_zero_total(self):
        sale = Sale.objects.create(store=self.store, created_by=self.user)
        self.assertEqual(sale.status, Sale.Status.DRAFT)
        self.assertIsNone(sale.customer_id)
        self.assertEqual(sale.total, Decimal("0.00"))

    def test_customer_must_belong_to_sale_store(self):
        customer = Customer.objects.create(store=self.other_store, name="Outra unidade")
        with self.assertRaises(ValidationError):
            Sale.objects.create(store=self.store, customer=customer, created_by=self.user)

    def test_inactive_customer_or_store_cannot_be_used(self):
        self.customer.is_active = False
        self.customer.save(update_fields=["is_active"])
        with self.assertRaises(ValidationError):
            Sale.objects.create(store=self.store, customer=self.customer, created_by=self.user)
        self.store.is_active = False
        self.store.save(update_fields=["is_active"])
        with self.assertRaises(ValidationError):
            Sale.objects.create(store=self.store, created_by=self.user)

    def test_product_must_belong_to_sale_store(self):
        product = Product.objects.create(store=self.other_store, internal_code="V002", name="Outro produto")
        with self.assertRaises(ValidationError):
            self.item(product=product)

    def test_quantity_and_discount_are_validated(self):
        for values in ({"quantity": Decimal("0")}, {"quantity": Decimal("-1")},
                       {"unit_price": Decimal("-1")}, {"discount_amount": Decimal("-1")},
                       {"discount_amount": Decimal("201")}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                self.item(**values)
        self.assertFalse(self.sale.items.exists())

    def test_totals_and_price_are_snapshots(self):
        item = self.item()
        self.assertEqual(item.unit_price, Decimal("100.00"))
        self.assertEqual(item.subtotal, Decimal("200.00"))
        self.assertEqual(self.sale.total, Decimal("190.00"))
        Product.objects.filter(pk=self.product.pk).update(name="Renomeado", sale_price=Decimal("150"))
        item.refresh_from_db()
        self.assertEqual(item.product_name, "Armação teste")
        self.assertEqual(item.unit_price, Decimal("100.00"))
        self.assertEqual(self.sale.total, Decimal("190.00"))

    def test_rounds_each_line_to_cents_using_half_up(self):
        item = self.item(quantity=Decimal("0.125"), unit_price=Decimal("0.04"), discount_amount=Decimal("0"))
        self.assertEqual(item.subtotal, Decimal("0.01"))
        self.assertEqual(self.sale.total, Decimal("0.01"))

    def test_discount_can_reduce_line_total_to_zero(self):
        item = self.item(discount_amount=Decimal("200"))
        self.assertEqual(item.total, Decimal("0.00"))

    def test_multiple_items_totals_and_deletion(self):
        item = self.item()
        second = Product.objects.create(store=self.store, internal_code="V002", name="Lente", sale_price=Decimal("50"))
        SaleItem.objects.create(sale=self.sale, product=second, quantity=Decimal("3"), discount_amount=Decimal("5"))
        self.assertEqual(self.sale.calculate_totals(), {
            "subtotal": Decimal("350.00"), "discount_total": Decimal("15.00"), "total": Decimal("335.00"),
        })
        item.delete()
        self.assertEqual(self.sale.total, Decimal("145.00"))

    def test_draft_does_not_change_stock(self):
        self.item()
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("10"))
        self.assertFalse(StockMovement.objects.exists())

    def test_duplicate_product_in_same_sale_is_rejected(self):
        self.item()
        with self.assertRaises(ValidationError):
            self.item()

    def test_database_rejects_negative_quantity(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            SaleItem.objects.bulk_create([SaleItem(
                sale=self.sale, product=self.product, quantity=Decimal("-1"), unit_price=Decimal("100"),
            )])

    def test_regular_save_cannot_finalize_sale(self):
        self.sale.status = Sale.Status.COMPLETED
        self.sale.completed_at = timezone.now()
        with self.assertRaises(ValidationError):
            self.sale.save()
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.Status.DRAFT)

    def test_completed_sale_and_items_are_protected_against_stale_edits(self):
        item = self.item()
        self.mark_completed_for_guard_test()
        with self.assertRaises(ValidationError):
            item.save()
        with self.assertRaises(ValidationError):
            item.delete()
        with self.assertRaises(ValidationError):
            self.sale.save()
        with self.assertRaises(ValidationError):
            self.sale.delete()

    def test_items_and_sale_cannot_move_to_other_store(self):
        item = self.item()
        other = Sale.objects.create(store=self.other_store, created_by=self.user)
        item.sale = other
        with self.assertRaises(ValidationError):
            item.save()
        self.sale.store = self.other_store
        with self.assertRaises(ValidationError):
            self.sale.save()

    def test_inactive_product_is_rejected(self):
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])
        with self.assertRaises(ValidationError):
            self.item()
