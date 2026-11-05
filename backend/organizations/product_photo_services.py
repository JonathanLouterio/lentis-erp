"""Três posições fixas, revisão otimista e troca atômica dos vínculos."""
import logging
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import APIException, PermissionDenied, NotFound, ValidationError
from accounts.selectors import get_accessible_stores
from .models import Product
from .product_photo_models import ProductPhoto, ProductPhotoAsset
from .product_photo_storage import PhotoStorage, PhotoStorageUnavailable

logger = logging.getLogger(__name__)


class GalleryConflict(APIException):
    status_code = 409
    default_detail = 'As fotos foram alteradas em outra sessão. Feche a janela, atualize a lista e reabra o produto antes de salvar.'


class GalleryInput(serializers.Serializer):
    revision = serializers.IntegerField(min_value=0, max_value=2147483647)
    remove = serializers.ListField(child=serializers.IntegerField(min_value=1, max_value=3), max_length=3, default=list)
    primary = serializers.IntegerField(min_value=1, max_value=3, allow_null=True, required=False)

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise ValidationError({'non_field_errors': ['Informe somente revision, remove e primary para as fotos.']})
        return super().to_internal_value(data)


def photo_url(product_id, store_id, slot, variant='thumb', version=None):
    path = f'/api/me/products/{product_id}/photos/{slot}/{variant}/?store_id={store_id}'
    return path + (f'&v={version}' if version else '')


def product_thumbnail(product):
    slot = product.primary_photo_slot
    return photo_url(product.pk, product.store_id, slot, version=product.photos_revision) if slot else None


def photo_output(product):
    return [{'slot': photo.slot, 'primary': product.primary_photo_slot == photo.slot,
             'url': photo_url(product.pk, product.store_id, photo.slot, 'image', photo.asset_id),
             'thumbnail_url': photo_url(product.pk, product.store_id, photo.slot, 'thumb', photo.asset_id)}
            for photo in product.photos.all()]


def purge_asset(asset):
    """Fica rastreável no banco se o serviço de objetos estiver indisponível."""
    if ProductPhoto.objects.filter(asset=asset).exists():
        return False
    storage = PhotoStorage(asset.storage)
    for variant in ('image', 'thumb'):
        storage.delete(asset.key(variant))
    asset.delete()
    return True


def try_purge(asset):
    try:
        purge_asset(asset)
    except Exception:
        # Não registra URLs, credenciais, corpo da requisição ou exceções do SDK.
        logger.warning('Limpeza de foto pendente; execute cleanup_product_photos. asset=%s', asset.pk)


def save_catalog_product(*, instance, values, gallery, uploads, actor, clean):
    staged = {}
    store = values.get('store') if instance is None else instance.store
    try:
        if uploads:
            try:
                storage = PhotoStorage()
                for slot, images in uploads.items():
                    asset = ProductPhotoAsset.objects.create(store=store,
                        company_id_snapshot=store.company_id, storage=storage.kind)
                    staged[slot] = asset
                    for variant, content in images.items():
                        storage.put(asset.key(variant), content)
            except Exception as exc:
                raise PhotoStorageUnavailable() from exc

        with transaction.atomic():
            # A gestão administrativa também bloqueia a linha do usuário ao revogar vínculos.
            user = get_user_model().objects.select_for_update().filter(pk=actor.pk, is_active=True).first()
            action = 'add' if instance is None else 'change'
            if not user or not user.has_perm(f'organizations.{action}_product'):
                raise PermissionDenied('Você não tem permissão para salvar produtos.')
            if not get_accessible_stores(user).filter(pk=store.pk).exists():
                raise PermissionDenied('Seu acesso à unidade foi revogado.')
            locked = Product(store=store) if instance is None else Product.objects.select_for_update().get(pk=instance.pk)
            if instance is not None and (locked.store_id != store.pk or not locked.is_active):
                raise NotFound('Produto indisponível nesta unidade.')
            if gallery is not None and gallery['revision'] != locked.photos_revision:
                raise GalleryConflict()
            for field, value in values.items():
                setattr(locked, field, value)
            clean(locked)
            locked.save() if instance is None else locked.save(update_fields=[*values, 'updated_at'])
            if gallery is not None:
                current = {p.slot: p for p in locked.photos.select_related('asset')}
                remove = set(gallery['remove'])
                remaining = (set(current) - remove) | set(staged)
                primary = gallery.get('primary', locked.primary_photo_slot)
                if primary not in remaining:
                    if gallery.get('primary') is not None:
                        raise ValidationError({'gallery': 'A foto principal precisa ocupar uma das três posições.'})
                    primary = min(remaining) if remaining else None
                retired = []
                for slot in remove | set(staged):
                    if slot in current:
                        retired.append(current[slot].asset)
                        current[slot].delete()
                for slot, asset in staged.items():
                    ProductPhoto.objects.create(product=locked, slot=slot, asset=asset)
                locked.primary_photo_slot = primary
                locked.photos_revision += 1
                locked.save(update_fields=['primary_photo_slot', 'photos_revision', 'updated_at'])
                for asset in retired:
                    transaction.on_commit(lambda asset=asset: try_purge(asset))
            return locked
    except Exception:
        for asset in staged.values():
            try_purge(asset)
        raise
