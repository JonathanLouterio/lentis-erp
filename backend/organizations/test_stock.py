from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from .models import Company, Product, StockMovement, Store
from .stock_services import register_stock_movement


class StockMovementTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="stock_admin", email="stock@example.com", password="test-only-password",
        )
        company = Company.objects.create(name="Empresa teste")
        self.store = Store.objects.create(company=company, code="01", name="Matriz")
        self.other_store = Store.objects.create(company=company, code="02", name="Filial")
        self.product = Product.objects.create(
            store=self.store, internal_code="P001", name="Armação teste",
            stock_quantity=Decimal("10.000"),
        )

    def register(self, **overrides):
        args = dict(
            user=self.user, store_id=self.store.pk, product_id=self.product.pk,
            movement_type="entry", quantity="2.500", reason="Conferência de estoque",
        )
        args.update(overrides)
        return register_stock_movement(**args)

    def assert_balance(self, expected):
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal(expected))

    def test_entry_records_balances_and_user(self):
        movement = self.register()
        self.assert_balance("12.500")
        self.assertEqual(movement.balance_before, Decimal("10"))
        self.assertEqual(movement.balance_after, Decimal("12.500"))
        self.assertEqual(movement.created_by, self.user)
        self.assertEqual(movement.store, self.store)

    def test_exit(self):
        self.register(movement_type="exit", quantity="3")
        self.assert_balance("7")

    def test_adjustment_sets_absolute_balance(self):
        movement = self.register(movement_type="adjustment", quantity="4")
        self.assert_balance("4")
        self.assertEqual(movement.quantity_change, Decimal("-6"))

    def test_adjustment_accepts_zero(self):
        self.register(movement_type="adjustment", quantity="0")
        self.assert_balance("0")

    def test_insufficient_stock_changes_nothing(self):
        with self.assertRaises(ValidationError):
            self.register(movement_type="exit", quantity="11")
        self.assert_balance("10")
        self.assertFalse(StockMovement.objects.exists())

    def test_invalid_values_change_nothing(self):
        for quantity in ("-1", "0", "NaN", "Infinity", "abc", "0.0001", "1000000000"):
            with self.subTest(quantity=quantity), self.assertRaises(ValidationError):
                self.register(quantity=quantity)
        self.assert_balance("10")
        self.assertFalse(StockMovement.objects.exists())

    def test_reason_is_required(self):
        with self.assertRaises(ValidationError):
            self.register(reason="   ")

    def test_product_from_another_store_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.register(store_id=self.other_store.pk)
        self.assert_balance("10")

    def test_inactive_product_is_rejected(self):
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])
        with self.assertRaises(ValidationError):
            self.register()

    def test_unlinked_user_is_denied(self):
        user = get_user_model().objects.create_user(username="stock_unlinked")
        with self.assertRaises(PermissionDenied):
            self.register(user=user)

    def test_inactive_user_is_denied(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        with self.assertRaises(PermissionDenied):
            self.register()

    def test_failure_rolls_back_history_and_balance(self):
        with patch.object(Product, "save", side_effect=RuntimeError("Test failure")):
            with self.assertRaises(RuntimeError):
                self.register()
        self.assert_balance("10")
        self.assertFalse(StockMovement.objects.exists())

    def test_movement_cannot_be_edited_or_deleted(self):
        movement = self.register()
        movement.reason = "Alteração"
        with self.assertRaises(ValidationError):
            movement.save()
        with self.assertRaises(ValidationError):
            movement.delete()
