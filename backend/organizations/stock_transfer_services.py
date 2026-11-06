from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.selectors import get_accessible_stores

from .models import Product, StockMovement
from .stock_services import register_stock_movement
from .stock_transfer_models import StockTransfer, StockTransferItem


def transfer_capabilities(user):
    allowed = user.has_perm("organizations.view_stocktransfer")
    return {key: allowed and user.has_perm(f"organizations.{key}_stocktransfer")
            for key in ("view", "add", "receive", "return")}


def for_store(store_id):
    return Q(source_id=store_id) | Q(destination_id=store_id)


def eligible_destinations(user, source):
    return get_accessible_stores(user).filter(company_id=source.company_id).exclude(pk=source.pk)


def product_key(product):
    return ("barcode", product.barcode) if product.barcode else ("internal_code", product.internal_code)


def locked_actor(user, store_id, action):
    if not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Entre com uma conta ativa.")
    actor = get_user_model().objects.select_for_update(no_key=True).filter(pk=user.pk, is_active=True).first()
    if not actor or not transfer_capabilities(actor)[action] or not get_accessible_stores(actor).filter(pk=store_id).exists():
        raise PermissionDenied("Você não tem acesso a esta ação nesta unidade.")
    return actor


@transaction.atomic
def dispatch_transfer(*, user, source, destination_id, request_id, note, items):
    actor = locked_actor(user, source.pk, "add")
    destination = eligible_destinations(actor, source).filter(pk=destination_id).first()
    if destination is None:
        raise ValidationError("Selecione outra unidade ativa da mesma empresa à qual você tenha acesso.")

    previous = StockTransfer.objects.filter(request_id=request_id).first()
    requested = {(line["source_product_id"], line["destination_product_id"], line["quantity"]) for line in items}
    if previous:
        if previous.source_id != source.pk or previous.sent_by_id != actor.pk:
            raise PermissionDenied("Este envio pertence a outra conta ou unidade.")
        if (previous.destination_id != destination_id or previous.note != note or
                set(previous.items.values_list("source_product_id", "destination_product_id", "quantity")) != requested):
            raise ValidationError("Este identificador já foi usado com outros dados.")
        return previous

    ids = {product_id for left, right, _ in requested for product_id in (left, right)}
    products = {
        p.pk: p for p in Product.objects.select_for_update(of=("self",)).filter(
            pk__in=ids, store_id__in=(source.pk, destination_id), is_active=True,
        ).order_by("pk")
    }
    for left, right, quantity in requested:
        origin, target = products.get(left), products.get(right)
        if (not origin or not target or origin.store_id != source.pk or target.store_id != destination_id
                or product_key(origin) != product_key(target)):
            raise ValidationError("Os produtos devem estar ativos e ter o mesmo código de barras ou, quando ambos não têm barras, o mesmo código interno.")
        if origin.stock_quantity < quantity:
            raise ValidationError(f"Estoque insuficiente na origem para {origin}.")

    transfer = StockTransfer.objects.create(
        source=source, destination=destination, request_id=request_id, note=note, sent_by=actor,
    )
    for left, right, quantity in sorted(requested):
        movement = register_stock_movement(
            user=actor, store_id=source.pk, product_id=left, movement_type=StockMovement.MovementType.EXIT,
            quantity=quantity, reason=f"Transferência #{transfer.pk}: enviada para {destination.name}.",
        )
        StockTransferItem.objects.create(
            transfer=transfer, source_product_id=left, destination_product_id=right,
            source_label=str(products[left]), destination_label=str(products[right]), quantity=quantity,
            outgoing_movement=movement,
        )
    return transfer


@transaction.atomic
def resolve_transfer(*, user, store, transfer_id, action, request_id, note):
    actor = locked_actor(user, store.pk, action)
    transfer = StockTransfer.objects.select_for_update().filter(for_store(store.pk), pk=transfer_id).first()
    if transfer is None:
        raise PermissionDenied("Transferência indisponível nesta unidade.")
    receiving = action == "receive"
    if store.pk != (transfer.destination_id if receiving else transfer.source_id):
        raise PermissionDenied("Confirme a operação pela unidade responsável.")
    target_status = StockTransfer.Status.RECEIVED if receiving else StockTransfer.Status.RETURNED
    if transfer.status != StockTransfer.Status.IN_TRANSIT:
        if (transfer.status == target_status and transfer.resolved_request_id == request_id
                and transfer.resolved_by_id == actor.pk and transfer.resolution_note == note):
            return transfer
        raise ValidationError("Esta transferência já foi encerrada.")
    if not receiving and not note:
        raise ValidationError("Informe o motivo da devolução à origem.")

    items = list(transfer.items.all())
    product_field = "destination_product_id" if receiving else "source_product_id"
    ids = [getattr(item, product_field) for item in items]
    locked_ids = list(Product.objects.select_for_update(of=("self",)).filter(
        pk__in=ids, store=store,
    ).order_by("pk").values_list("pk", flat=True))
    if len(locked_ids) != len(ids):
        raise ValidationError("Um produto deixou de pertencer à unidade desta operação.")
    for item in items:
        movement = register_stock_movement(
            user=actor, store_id=store.pk, product_id=getattr(item, product_field), quantity=item.quantity,
            movement_type=StockMovement.MovementType.ENTRY, _allow_inactive=not receiving,
            reason=f"Transferência #{transfer.pk}: {'recebida na unidade de destino' if receiving else 'devolvida à origem'}.",
        )
        item.incoming_movement = movement
        item.save(update_fields=["incoming_movement"])
    transfer.status = target_status
    transfer.resolved_request_id = request_id
    transfer.resolved_by = actor
    transfer.resolved_at = timezone.now()
    transfer.resolution_note = note
    transfer.save(update_fields=["status", "resolved_request_id", "resolved_by", "resolved_at", "resolution_note"])
    return transfer
