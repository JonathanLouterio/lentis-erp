from django.conf import settings
from django.db import models


class StockTransfer(models.Model):
    class Status(models.TextChoices):
        IN_TRANSIT = "in_transit", "Em trânsito"
        RECEIVED = "received", "Recebida"
        RETURNED = "returned", "Devolvida à origem"

    source = models.ForeignKey("organizations.Store", on_delete=models.PROTECT, related_name="outgoing_transfers")
    destination = models.ForeignKey("organizations.Store", on_delete=models.PROTECT, related_name="incoming_transfers")
    request_id = models.UUIDField(unique=True, editable=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.IN_TRANSIT)
    note = models.CharField(max_length=255, blank=True)
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    sent_at = models.DateTimeField(auto_now_add=True)
    resolved_request_id = models.UUIDField(null=True, unique=True, editable=False)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+")
    resolved_at = models.DateTimeField(null=True)
    resolution_note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-pk"]
        verbose_name = "Transferência de estoque"
        verbose_name_plural = "Transferências de estoque"
        default_permissions = ("view", "add")
        permissions = [
            ("receive_stocktransfer", "Pode confirmar recebimento de transferência"),
            ("return_stocktransfer", "Pode confirmar devolução de transferência à origem"),
        ]
        constraints = [
            models.CheckConstraint(condition=~models.Q(source=models.F("destination")), name="stock_transfer_distinct_units"),
            models.CheckConstraint(condition=(
                models.Q(status="in_transit", resolved_request_id__isnull=True, resolved_by__isnull=True, resolved_at__isnull=True)
                | models.Q(status__in=["received", "returned"], resolved_request_id__isnull=False, resolved_by__isnull=False, resolved_at__isnull=False)
            ), name="stock_transfer_resolution_consistent"),
        ]


class StockTransferItem(models.Model):
    transfer = models.ForeignKey(StockTransfer, on_delete=models.PROTECT, related_name="items")
    source_product = models.ForeignKey("organizations.Product", on_delete=models.PROTECT, related_name="+")
    destination_product = models.ForeignKey("organizations.Product", on_delete=models.PROTECT, related_name="+")
    source_label = models.CharField(max_length=215)
    destination_label = models.CharField(max_length=215)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    outgoing_movement = models.OneToOneField("organizations.StockMovement", on_delete=models.PROTECT, related_name="+")
    incoming_movement = models.OneToOneField("organizations.StockMovement", null=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["pk"]
        default_permissions = ()
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="stock_transfer_positive_quantity"),
            models.UniqueConstraint(fields=["transfer", "source_product"], name="stock_transfer_unique_source_product"),
            models.UniqueConstraint(fields=["transfer", "destination_product"], name="stock_transfer_unique_destination_product"),
        ]
