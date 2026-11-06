from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from accounts.models import StoreMembership

from .models import Company, Product, StockMovement, Store
from .stock_transfer_models import StockTransfer


class TransferFixture:
    def setUp(self):
        company = Company.objects.create(name="Ótica teste")
        self.source = Store.objects.create(company=company, code="01", name="Matriz", allow_negative_stock=True)
        self.target = Store.objects.create(company=company, code="02", name="Filial")
        self.other = Store.objects.create(company=Company.objects.create(name="Outra ótica"), code="03", name="Outra")
        self.sender = self.operator("sender", (self.source, self.target, self.other), "add", "return")
        self.receiver = self.operator("receiver", (self.target,), "receive")
        self.origin = Product.objects.create(
            store=self.source, internal_code="OR01", barcode="MATCH1", name="Armação", stock_quantity=Decimal("10"),
        )
        self.match = Product.objects.create(
            store=self.target, internal_code="FI01", barcode="MATCH1", name="Armação filial", stock_quantity=Decimal("3"),
        )
        self.origin2 = Product.objects.create(store=self.source, internal_code="SEM", name="Lente", stock_quantity=Decimal("5"))
        self.match2 = Product.objects.create(store=self.target, internal_code="SEM", name="Lente")
        self.client = APIClient()
        self.client.force_authenticate(self.sender)

    def operator(self, username, stores, *rights):
        user = get_user_model().objects.create_user(username=username, password="test-only-password")
        for store in stores:
            StoreMembership.objects.create(user=user, store=store, role=StoreMembership.Role.SELLER)
        user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="organizations",
            codename__in=[f"{action}_stocktransfer" for action in ("view", *rights)],
        ))
        return user

    def url(self, store, part=""):
        return f"/api/me/stock-transfers/{part}?store_id={store.pk}"

    def payload(self, quantity="2.500", **overrides):
        return {
            "destination_id": self.target.pk, "request_id": str(uuid4()), "note": "Reposição",
            "items": [{"source_product_id": self.origin.pk, "destination_product_id": self.match.pk, "quantity": quantity}],
            **overrides,
        }

    def dispatch(self, data=None):
        return self.client.post(self.url(self.source), data or self.payload(), format="json")

    def resolution(self, transfer, store, action, **overrides):
        data = {"action": action, "request_id": str(uuid4()), **overrides}
        return self.client.post(self.url(store, f"{transfer}/"), data, format="json")

    def assert_stock(self, product, amount):
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, Decimal(amount))


class StockTransferTests(TransferFixture, TestCase):
    def test_send_then_receive_once_and_write_each_stores_history(self):
        payload = self.payload()
        sent = self.dispatch(payload)
        self.assertEqual(sent.status_code, 201, sent.data)
        self.assertEqual(sent.data["status"], "in_transit")
        self.assertTrue(sent.data["can_return"])
        self.assertFalse(sent.data["can_receive"])
        self.assert_stock(self.origin, "7.5")
        self.assert_stock(self.match, "3")
        self.assertEqual(self.dispatch(payload).data["id"], sent.data["id"])
        self.assertEqual(self.dispatch({**payload, "note": "Mudou"}).status_code, 400)
        self.assertEqual(StockMovement.objects.count(), 1)

        self.client.force_authenticate(self.receiver)
        catalog = self.client.get(f"/api/me/catalog-access/?store_id={self.target.pk}")
        self.assertTrue(catalog.data["transfers"]["receive"])
        self.assertFalse(catalog.data["stock"]["add"])
        listed = self.client.get(self.url(self.target) + "&direction=incoming&status=in_transit").data
        self.assertTrue(listed["results"][0]["can_receive"])
        request_id = str(uuid4())
        received = self.resolution(sent.data["id"], self.target, "receive", request_id=request_id)
        self.assertEqual(received.status_code, 200, received.data)
        self.assertEqual(received.data["status"], "received")
        self.assertEqual(received.data["resolved_by"], self.receiver.username)
        self.assertEqual(self.resolution(sent.data["id"], self.target, "receive", request_id=request_id).status_code, 200)
        self.assertEqual(self.resolution(sent.data["id"], self.target, "receive").status_code, 400)
        self.assert_stock(self.match, "5.5")
        self.assert_stock(self.origin, "7.5")
        self.assertEqual(StockMovement.objects.count(), 2)
        for key, store, movement_type in (
            ("outgoing_movement_id", self.source, "exit"), ("incoming_movement_id", self.target, "entry"),
        ):
            movement = StockMovement.objects.get(pk=received.data["items"][0][key])
            self.assertEqual((movement.store_id, movement.movement_type), (store.pk, movement_type))
            self.assertIn(f'#{sent.data["id"]}', movement.reason)

    def test_options_scope_and_no_mismatched_items_even_if_manually_posted(self):
        options = self.client.get(self.url(self.source, "options/")).data
        self.assertEqual([item["id"] for item in options["destinations"]], [self.target.pk])
        options = self.client.get(self.url(self.source, "options/") + f"&destination_id={self.target.pk}").data
        self.assertEqual({(p["source_product_id"], p["destination_product_id"]) for p in options["products"]},
                         {(self.origin.pk, self.match.pk), (self.origin2.pk, self.match2.pk)})
        self.assertNotIn("cost_price", options["products"][0])
        for store in (self.source, self.other):
            self.assertEqual(self.dispatch(self.payload(destination_id=store.pk)).status_code, 400)
        self.match.barcode = "DIFFERENT"
        self.match.internal_code = self.origin.internal_code
        self.match.save()
        self.assertEqual(self.dispatch().status_code, 400)
        self.assertFalse(StockTransfer.objects.exists())
        self.assertFalse(StockMovement.objects.exists())

    def test_dispatch_always_blocks_negative_stock_and_rolls_back_the_whole_transfer(self):
        data = self.payload()
        data["items"].append({"source_product_id": self.origin2.pk, "destination_product_id": self.match2.pk, "quantity": "6"})
        response = self.dispatch(data)
        self.assertEqual(response.status_code, 400, response.data)
        self.assert_stock(self.origin, "10")
        self.assert_stock(self.origin2, "5")
        self.assertFalse(StockMovement.objects.exists())
        for quantity in ("0", "-1", "0.0001"):
            self.assertEqual(self.dispatch(self.payload(quantity)).status_code, 400)

    def test_receipt_rolls_back_if_second_product_unavailable_and_source_can_confirm_return(self):
        data = self.payload()
        data["items"].append({"source_product_id": self.origin2.pk, "destination_product_id": self.match2.pk, "quantity": "1"})
        sent = self.dispatch(data)
        self.assertEqual(sent.status_code, 201, sent.data)
        self.match2.is_active = False
        self.match2.save(update_fields=["is_active"])
        self.client.force_authenticate(self.receiver)
        self.assertEqual(self.resolution(sent.data["id"], self.target, "receive").status_code, 400)
        self.assert_stock(self.match, "3")
        self.assertEqual(StockMovement.objects.count(), 2)
        self.assertEqual(StockTransfer.objects.get().status, "in_transit")
        self.client.force_authenticate(self.sender)
        self.assertEqual(self.resolution(sent.data["id"], self.source, "return").status_code, 400)
        self.origin2.is_active = False
        self.origin2.save(update_fields=["is_active"])
        returned = self.resolution(sent.data["id"], self.source, "return", note="Mercadoria voltou fisicamente")
        self.assertEqual(returned.status_code, 200, returned.data)
        self.assertEqual(returned.data["status"], "returned")
        self.assert_stock(self.origin, "10")
        self.assert_stock(self.origin2, "5")
        self.assert_stock(self.match, "3")
        self.client.force_authenticate(self.receiver)
        self.assertEqual(self.resolution(sent.data["id"], self.target, "receive").status_code, 400)
        self.assertEqual(StockMovement.objects.count(), 4)

    def test_access_rules_for_origin_destination_and_unrelated_store(self):
        sent = self.dispatch()
        self.assertEqual(sent.status_code, 201, sent.data)
        tid = sent.data["id"]
        self.assertEqual(self.client.get(self.url(self.other, f"{tid}/")).status_code, 404)
        self.assertEqual(self.resolution(tid, self.target, "return", note="Unidade errada").status_code, 403)
        self.assertEqual(self.resolution(tid, self.target, "receive").status_code, 403)
        self.client.force_authenticate(self.receiver)
        self.assertEqual(self.client.get(self.url(self.source)).status_code, 400)
        self.assertEqual(self.client.post(self.url(self.target), self.payload(), format="json").status_code, 403)
        self.assertEqual(self.resolution(tid, self.target, "return", note="Sem permissão").status_code, 403)
        self.receiver.user_permissions.remove(Permission.objects.get(codename="receive_stocktransfer"))
        self.assertEqual(self.resolution(tid, self.target, "receive").status_code, 403)
        self.client.force_authenticate(self.sender)
        StoreMembership.objects.filter(store=self.target, user=self.sender).update(is_active=False)
        self.assertEqual(self.dispatch().status_code, 400)
        self.assertEqual(StockMovement.objects.count(), 1)


@skipUnless(connection.vendor == "postgresql", "Requer bloqueio de linhas do PostgreSQL")
class ConcurrentStockTransferTests(TransferFixture, TransactionTestCase):
    def test_two_operators_cannot_both_dispatch_the_last_units(self):
        other_sender = self.operator("sender2", (self.source, self.target), "add")
        start = Barrier(2)
        url = self.url(self.source)

        def send(user_id, payload):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(get_user_model().objects.get(pk=user_id))
                start.wait(timeout=10)
                return client.post(url, payload, format="json").status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(send, self.sender.pk, self.payload("8"))
            b = pool.submit(send, other_sender.pk, self.payload("8"))
            self.assertEqual(sorted([a.result(timeout=20), b.result(timeout=20)]), [201, 400])
        self.assert_stock(self.origin, "2")
        self.assert_stock(self.match, "3")
        self.assertEqual(StockMovement.objects.count(), 1)
