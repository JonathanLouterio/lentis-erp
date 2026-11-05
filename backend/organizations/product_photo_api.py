from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from .access_permissions import fresh_actor, FreshActiveUser
from .views import SelectedStoreMixin
from .models import Product
from .product_photo_models import ProductPhoto
from .product_photo_storage import PhotoStorage, PhotoStorageUnavailable


class ProductPhotoView(SelectedStoreMixin, APIView):
    permission_classes = [IsAuthenticated, FreshActiveUser]
    http_method_names = ['get', 'head', 'options']

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        response['Vary'] = 'Cookie'
        response['X-Content-Type-Options'] = 'nosniff'
        return response

    def get(self, request, product_id, slot, variant):
        from sales.access_permissions import sale_capabilities
        from purchases.access_permissions import purchase_capabilities
        user = fresh_actor(request)
        store = self._selected_store()
        if slot not in (1, 2, 3) or variant not in ('image', 'thumb'):
            from rest_framework.exceptions import NotFound
            raise NotFound()
        # Mesmos consumidores autorizados dos catálogos reduzidos e dos itens históricos.
        if not (user.has_perm('organizations.view_product') or user.has_perm('organizations.change_product')
                or any(sale_capabilities(user).values()) or purchase_capabilities(user)['view']):
            raise PermissionDenied('Seu usuário não tem acesso às fotos de produtos.')
        product = get_object_or_404(Product, pk=product_id, store=store)
        photo = get_object_or_404(ProductPhoto.objects.select_related('asset'), product=product, slot=slot)
        if photo.asset.store_id != store.pk or photo.asset.company_id_snapshot != store.company_id:
            raise PermissionDenied('Foto indisponível nesta unidade.')
        try:
            content = PhotoStorage(photo.asset.storage).get(photo.asset.key(variant), variant)
        except Exception as exc:
            raise PhotoStorageUnavailable() from exc
        return HttpResponse(content, content_type='image/jpeg', headers={'Content-Disposition': 'inline; filename="produto.jpg"'})
