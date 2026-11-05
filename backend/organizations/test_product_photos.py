"""Galeria, isolamento de mídias e integração com catálogos comerciais."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest import skipUnless
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ImproperlyConfigured
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from accounts.models import StoreMembership
from .models import Company, Store, Product, StockMovement, ProductPhoto, ProductPhotoAsset
from .product_images import MAX_UPLOAD, normalize_product_photo
from .product_photo_storage import PhotoStorage, r2_client
from .product_photo_services import photo_url

User = get_user_model()


def picture(fmt='PNG', size=(500, 300), color='purple', **options):
    out = BytesIO()
    with Image.new('RGB', size, color) as image:
        image.save(out, fmt, **options)
    return SimpleUploadedFile('particular.' + fmt.lower(), out.getvalue(), content_type='image/' + fmt.lower())


@override_settings(DEBUG=True, PRODUCT_PHOTO_STORAGE='local')
class ProductPhotosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='photos', password='test-password')
        cls.user.user_permissions.add(*Permission.objects.filter(content_type__app_label='organizations', content_type__model='product'))
        cls.company = Company.objects.create(name='Ótica principal')
        cls.store = Store.objects.create(company=cls.company, code='P1', name='Matriz')
        cls.other = Store.objects.create(company=cls.company, code='P2', name='Outra unidade')
        cls.other_company = Company.objects.create(name='Outra ótica')
        cls.foreign = Store.objects.create(company=cls.other_company, code='PF1', name='Outra empresa')
        StoreMembership.objects.create(user=cls.user, store=cls.store, role='seller')
        cls.product = Product.objects.create(store=cls.store, internal_code='A1', name='Armação inicial', stock_quantity='10', sale_price='120', cost_price='50')

    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.setting = override_settings(PRODUCT_PHOTO_LOCAL_ROOT=self.directory.name)
        self.setting.enable(); self.addCleanup(self.setting.disable)
        self.client = APIClient(); self.client.force_authenticate(self.user)

    def url(self, product=None, store=None):
        return f'/api/me/products/{(product or self.product).pk}/?store_id={(store or self.store).pk}'

    def save(self, *, files=None, revision=None, gallery=None, **values):
        self.product.refresh_from_db()
        if gallery is None:
            gallery = {'revision': self.product.photos_revision if revision is None else revision, 'remove': []}
        data = {'data': json.dumps({**values, 'gallery': gallery}), **(files or {})}
        return self.client.patch(self.url(), data, format='multipart')

    def upload(self, slot=1):
        response = self.save(files={f'photo_{slot}': picture()})
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def photo(self, slot=1, variant='thumb', store=None):
        return photo_url(self.product.pk, (store or self.store).pk, slot, variant)

    def assert_untouched(self):
        self.product.refresh_from_db()
        self.assertEqual(str(self.product.stock_quantity), '10.000')
        self.assertEqual(str(self.product.sale_price), '120.00')
        self.assertEqual(str(self.product.cost_price), '50.00')
        self.assertFalse(StockMovement.objects.exists())

    def test_existing_product_has_empty_gallery_without_storage_access(self):
        with patch('organizations.product_photo_storage.r2_client') as client:
            response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['photos'], [])
        self.assertIsNone(response.data['thumbnail_url'])
        self.assertEqual(response.data['photos_revision'], 0)
        client.assert_not_called()

    def test_create_product_and_three_photos_in_one_request(self):
        data = {'internal_code': 'N1', 'name': 'Óculos novo', 'brand': 'Lentis', 'model_reference': 'LN2026',
            'color': 'Âmbar', 'material': 'Acetato', 'frame_shape': 'Redondo', 'lens_width_mm': '52.5',
            'bridge_mm': '18.0', 'temple_mm': '140.0', 'description': 'Peça de teste',
            'gallery': {'revision': 0, 'primary': 2}}
        response = self.client.post(f'/api/me/products/?store_id={self.store.pk}',
            {'data': json.dumps(data), **{f'photo_{n}': picture(color=c) for n, c in enumerate(['red','green','blue'], 1)}}, format='multipart')
        self.assertEqual(response.status_code, 201, response.data)
        product = Product.objects.get(pk=response.data['id'])
        self.assertEqual(product.primary_photo_slot, 2)
        self.assertEqual(product.photos.count(), 3)
        self.assertEqual(response.data['photos'][1]['primary'], True)
        self.assertEqual(response.data['lens_width_mm'], '52.5')
        self.assertEqual(product.stock_quantity, 0)
        self.assertEqual(len(list(Path(self.directory.name).rglob('*.jpg'))), 6)
        self.assertNotIn('particular', str(response.data))
        self.assertNotIn('cloudflarestorage', str(response.data))

    def test_primary_selection_changes_thumbnail_without_reupload(self):
        self.upload()
        self.upload(3)
        before = ProductPhotoAsset.objects.count()
        response = self.save(gallery={'revision': 2, 'primary': 3})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('/photos/3/thumb/', response.data['thumbnail_url'])
        self.assertEqual(ProductPhotoAsset.objects.count(), before)
        self.assert_untouched()

    def test_remove_primary_chooses_remaining_then_no_photo(self):
        self.upload(1); self.upload(3)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.save(gallery={'revision': 2, 'remove': [1]})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['primary_photo_slot'], 3)
        self.assertEqual(self.client.get(self.photo(1)).status_code, 404)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.save(gallery={'revision': 3, 'remove': [3], 'primary': None})
        self.assertIsNone(response.data['thumbnail_url'])
        self.assertFalse(ProductPhoto.objects.exists())
        self.assertFalse(ProductPhotoAsset.objects.exists())
        self.assert_untouched()

    def test_replacing_one_slot_preserves_other_photos(self):
        self.upload(); self.upload(2)
        old = ProductPhoto.objects.get(product=self.product, slot=1).asset_id
        other = ProductPhoto.objects.get(product=self.product, slot=2).asset_id
        with self.captureOnCommitCallbacks(execute=True):
            response = self.save(files={'photo_1': picture(color='orange')})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(ProductPhotoAsset.objects.filter(pk=old).exists())
        self.assertTrue(ProductPhotoAsset.objects.filter(pk=other).exists())
        self.assertEqual(ProductPhoto.objects.count(), 2)
        self.assert_untouched()

    def test_repeated_stale_submission_does_not_duplicate_photos_or_modify_text(self):
        self.upload()
        response = self.save(files={'photo_2': picture()}, revision=0, name='Não salvar')
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(ProductPhoto.objects.count(), 1)
        self.assertEqual(ProductPhotoAsset.objects.count(), 1)
        self.product.refresh_from_db(); self.assertEqual(self.product.name, 'Armação inicial')

    def test_fourth_slot_unknown_file_and_duplicate_slot_are_rejected(self):
        for files in ({'photo_4': picture()}, {'file': picture()}, {'photo_1': [picture(), picture()]}):
            response = self.save(files=files)
            self.assertEqual(response.status_code, 413, response.data)
        self.assertFalse(ProductPhoto.objects.exists())

    def test_oversized_upload_is_rejected_before_decode(self):
        file = SimpleUploadedFile('huge.jpg', b'a' * (MAX_UPLOAD + 1), content_type='image/jpeg')
        with patch('organizations.product_images.Image.open') as decode:
            response = self.save(files={'photo_1': file})
        self.assertEqual(response.status_code, 413, response.data)
        decode.assert_not_called()

    def test_dimensions_and_animation_are_rejected(self):
        file = picture(size=(5000, 3300))
        with patch('organizations.product_images.ImageOps.exif_transpose') as transpose:
            response = self.save(files={'photo_1': file})
        self.assertEqual(response.status_code, 400, response.data)
        transpose.assert_not_called()
        out=BytesIO()
        with Image.new('RGB',(20,20),'red') as a, Image.new('RGB',(20,20),'green') as b:
            a.save(out, 'PNG', save_all=True, append_images=[b], duration=100, loop=0)
        response=self.save(files={'photo_1':SimpleUploadedFile('animated.png',out.getvalue())})
        self.assertEqual(response.status_code,400,response.data)
        self.assertFalse(ProductPhoto.objects.exists())

    def test_forged_or_corrupt_content_does_not_save_anything(self):
        for data in (b'<svg onload="alert(1)"/>', b'<html>bad</html>', b'\x89PNG\r\n\x1a\nBROKEN', picture('GIF').read()):
            response = self.save(files={'photo_1': SimpleUploadedFile('falso.jpg', data, content_type='image/jpeg')}, name='Não salvar')
            self.assertEqual(response.status_code, 400, response.data)
        self.product.refresh_from_db(); self.assertEqual(self.product.name, 'Armação inicial')
        self.assertFalse(ProductPhotoAsset.objects.exists())

    def test_jpeg_png_webp_orientation_transparency_and_metadata(self):
        exif = Image.Exif(); exif[274] = 6; exif[270] = 'Private GPS information'
        variants = [picture('JPEG', (120, 80), exif=exif), picture('PNG'), picture('WEBP')]
        for index, photo in enumerate(variants, 1):
            response = self.save(files={f'photo_{index}': photo})
            self.assertEqual(response.status_code, 200, response.data)
            binary = self.client.get(self.photo(index, 'image'))
            self.assertEqual(binary.status_code, 200)
            self.assertEqual(binary['Content-Type'], 'image/jpeg')
            self.assertIn('no-store', binary['Cache-Control'])
            self.assertEqual(binary['X-Content-Type-Options'], 'nosniff')
            with Image.open(BytesIO(binary.content)) as image:
                self.assertFalse(image.getexif())
                if index == 1:self.assertEqual(image.size, (80,120))
            self.assertNotIn(b'Private GPS', binary.content)
        out=BytesIO()
        with Image.new('RGBA',(10,10),(0,0,0,0)) as img:img.save(out,'PNG')
        clean=normalize_product_photo(SimpleUploadedFile('transparent.png',out.getvalue()))
        with Image.open(BytesIO(clean['image'])) as image:self.assertEqual(image.getpixel((0,0)),(255,255,255))

    def test_thumbnail_keeps_aspect_ratio_and_has_bounded_size(self):
        normalized=normalize_product_photo(picture(size=(2400,1600)))
        for variant, limit, dimensions in [('image',1024*1024,1600),('thumb',96*1024,240)]:
            self.assertLessEqual(len(normalized[variant]),limit)
            with Image.open(BytesIO(normalized[variant])) as image:
                self.assertEqual(max(image.size),dimensions)
                self.assertAlmostEqual(image.width/image.height,1.5,places=2)

    def test_invalid_gallery_cannot_save_text_or_leave_uploads(self):
        for gallery in ({'revision':0,'primary':3},{'revision':0,'remove':[4]}, {'revision':0,'key':'injected'}, {'remove':[]}, []):
            response=self.save(gallery=gallery,files={'photo_1':picture()},name='Não salvar')
            self.assertEqual(response.status_code,400,response.data)
        self.product.refresh_from_db();self.assertEqual(self.product.name,'Armação inicial')
        self.assertFalse(ProductPhoto.objects.exists())
        self.assertFalse(ProductPhotoAsset.objects.exists())

    def test_removing_and_uploading_same_slot_is_rejected(self):
        response=self.save(gallery={'revision':0,'remove':[1]},files={'photo_1':picture()})
        self.assertEqual(response.status_code,400,response.data)

    def test_files_require_gallery_and_json_must_be_valid(self):
        response=self.client.patch(self.url(),{'data':'{"name":"Other"}', 'photo_1':picture()},format='multipart')
        self.assertEqual(response.status_code,400,response.data)
        for data in ('{', '[]', 'null'):
            response=self.client.patch(self.url(),{'data':data},format='multipart')
            self.assertEqual(response.status_code,400,response.data)

    def test_is_active_guard_and_stock_guard_still_apply_to_multipart(self):
        for values in ({'is_active':False},{'stock_quantity':'99'}):
            response=self.save(files={'photo_1':picture()},**values)
            self.assertEqual(response.status_code,400,response.data)
        self.assert_untouched();self.product.refresh_from_db();self.assertTrue(self.product.is_active)

    def test_plain_json_metadata_edit_preserves_photos_and_stock(self):
        self.upload();before=self.client.get(self.photo()).content
        response=self.client.patch(self.url(),{'color':'Preto','model_reference':'L2026','bridge_mm':'18.5'},format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['bridge_mm'],'18.5')
        self.assertEqual(self.client.get(self.photo()).content,before)
        self.assert_untouched()

    def test_measurements_optional_positive_and_one_decimal(self):
        for value in ('0','-2','18.55','10000'):
            response=self.client.patch(self.url(),{'lens_width_mm':value},format='json')
            self.assertEqual(response.status_code,400,response.data)
        response=self.client.patch(self.url(),{'lens_width_mm':None,'description':'Sem medidas de armação'},format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertIsNone(response.data['lens_width_mm'])

    def test_storage_failure_rolls_back_text_and_cleans_both_objects(self):
        storage=Mock(kind='r2');storage.put.side_effect=[None,OSError('Secret that must not leak')]
        with patch('organizations.product_photo_services.PhotoStorage',return_value=storage),patch('organizations.product_photo_services.try_purge') as purge:
            response=self.save(files={'photo_1':picture()},name='Não salvar')
        self.assertEqual(response.status_code,503,response.data)
        self.assertNotIn('Secret',str(response.data))
        self.product.refresh_from_db();self.assertEqual(self.product.name,'Armação inicial')
        purge.assert_called_once()
        self.assertFalse(ProductPhoto.objects.exists())

    def test_database_failure_cleans_new_objects_and_preserves_existing_photo(self):
        self.upload();before=self.client.get(self.photo()).content
        with patch('organizations.product_photo_services.ProductPhoto.objects.create',side_effect=RuntimeError('DB failure')):
            with self.assertRaises(RuntimeError):self.save(files={'photo_1':picture(color='red')},name='Não salvar')
        self.product.refresh_from_db();self.assertEqual(self.product.name,'Armação inicial')
        self.assertEqual(self.client.get(self.photo()).content,before)
        self.assertEqual(ProductPhotoAsset.objects.count(),1)
        self.assertEqual(ProductPhoto.objects.count(),1)

    def test_failed_delete_is_retained_for_cleanup_retry(self):
        self.upload()
        with patch('organizations.product_photo_storage.PhotoStorage.delete',side_effect=OSError('offline')):
            with self.captureOnCommitCallbacks(execute=True):response=self.save(gallery={'revision':1,'remove':[1]})
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(ProductPhotoAsset.objects.count(),1)
        self.assertFalse(ProductPhoto.objects.exists())
        ProductPhotoAsset.objects.update(created_at=timezone.now()-timedelta(days=2))
        call_command('cleanup_product_photos','--apply',stdout=StringIO())
        self.assertFalse(ProductPhotoAsset.objects.exists())

    def test_cleanup_skips_linked_and_recent_assets_and_defaults_to_dry_run(self):
        self.upload()
        old=ProductPhotoAsset.objects.create(store=self.store,company_id_snapshot=self.company.pk,storage='local')
        ProductPhotoAsset.objects.filter(pk=old.pk).update(created_at=timezone.now()-timedelta(days=2))
        recent=ProductPhotoAsset.objects.create(store=self.store,company_id_snapshot=self.company.pk,storage='local')
        out=StringIO();call_command('cleanup_product_photos',stdout=out)
        self.assertIn('1 sobra(s)',out.getvalue());self.assertEqual(ProductPhotoAsset.objects.count(),3)
        call_command('cleanup_product_photos','--apply',stdout=StringIO())
        self.assertTrue(ProductPhotoAsset.objects.filter(pk=recent.pk).exists())
        self.assertEqual(ProductPhotoAsset.objects.count(),2)

    def test_busy_decoder_returns_429_without_saving_product(self):
        from .product_images import _slot
        with _slot:
            response=self.save(files={'photo_1':picture()},name='Não salvar')
        self.assertEqual(response.status_code,429,response.data)
        self.product.refresh_from_db();self.assertEqual(self.product.name,'Armação inicial')
        self.assertFalse(ProductPhotoAsset.objects.exists())

    def test_storage_diagnostic_roundtrip_and_dry_run(self):
        out=StringIO()
        with patch('organizations.management.commands.check_product_photo_storage.PhotoStorage') as factory:
            call_command('check_product_photo_storage',stdout=out)
            factory.return_value.put.assert_not_called()
        out=StringIO();call_command('check_product_photo_storage','--roundtrip',stdout=out)
        self.assertIn('Envio, leitura e remoção conferidos',out.getvalue())
        self.assertEqual(list(Path(self.directory.name).rglob('*.jpg')),[])
        self.assertFalse(ProductPhotoAsset.objects.exists())

    def test_permissions_revocation_and_inactive_user_deny_read_and_write(self):
        self.upload()
        self.user.user_permissions.clear()
        self.assertEqual(self.client.get(self.photo()).status_code,403)
        self.assertEqual(self.save(files={'photo_2':picture()}).status_code,403)
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.client.get(self.photo()).status_code,403)

    def test_anonymous_and_staff_without_permissions_are_denied(self):
        self.upload();self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.photo()).status_code,403)
        self.client.force_authenticate(self.user)
        self.user.user_permissions.clear();User.objects.filter(pk=self.user.pk).update(is_staff=True)
        self.assertEqual(self.client.get(self.photo()).status_code,403)

    def test_membership_revocation_and_inactive_store_or_company_deny_read(self):
        self.upload()
        StoreMembership.objects.filter(user=self.user).update(is_active=False)
        self.assertEqual(self.client.get(self.photo()).status_code,400)
        StoreMembership.objects.filter(user=self.user).update(is_active=True)
        Store.objects.filter(pk=self.store.pk).update(is_active=False)
        self.assertEqual(self.client.get(self.photo()).status_code,400)
        Store.objects.filter(pk=self.store.pk).update(is_active=True)
        Company.objects.filter(pk=self.company.pk).update(is_active=False)
        self.assertEqual(self.client.get(self.photo()).status_code,400)

    def test_other_units_and_other_company_are_never_exposed_by_ids(self):
        self.upload()
        for store in (self.other,self.foreign):
            self.assertEqual(self.client.get(self.photo(store=store)).status_code,400)
            StoreMembership.objects.create(user=self.user,store=store,role='seller')
            self.assertEqual(self.client.get(self.photo(store=store)).status_code,404)
            self.assertEqual(self.client.patch(self.url(store=store),{'name':'Ataque'},format='json').status_code,404)
        self.assert_untouched()

    def test_superuser_can_read_authorized_company_and_invalid_variants_are_404(self):
        self.upload();User.objects.filter(pk=self.user.pk).update(is_superuser=True)
        self.assertEqual(self.client.get(self.photo()).status_code,200)
        self.assertEqual(self.client.get(self.photo(4)).status_code,404)
        self.assertEqual(self.client.get(self.photo(1,'original')).status_code,404)

    def test_unit_and_permission_rechecked_after_storage_upload(self):
        storage=Mock(kind='local')
        def revoke(*args,**kwargs):StoreMembership.objects.filter(user=self.user).update(is_active=False)
        storage.put.side_effect=revoke
        with patch('organizations.product_photo_services.PhotoStorage',return_value=storage):
            response=self.save(files={'photo_1':picture()},name='Não salvar')
        self.assertEqual(response.status_code,403,response.data)
        self.assertFalse(ProductPhoto.objects.exists())
        self.product.refresh_from_db();self.assertEqual(self.product.name,'Armação inicial')

    def test_csrf_required_for_photo_changes(self):
        client=APIClient(enforce_csrf_checks=True);client.force_login(self.user)
        self.assertEqual(client.patch(self.url(),{'data':json.dumps({'gallery':{'revision':0}}),'photo_1':picture()},format='multipart').status_code,403)
        token=client.get('/api/auth/csrf/').json()['csrfToken']
        response=client.patch(self.url(),{'data':json.dumps({'gallery':{'revision':0}}),'photo_1':picture()},format='multipart',HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code,200,response.data)

    def test_only_sales_permission_can_see_photo_in_reduced_catalog_and_sale_items(self):
        self.upload();self.user.user_permissions.clear()
        self.user.user_permissions.add(Permission.objects.get(content_type__app_label='sales',codename='view_sale'))
        response=self.client.get(f'/api/me/sales/options/?store_id={self.store.pk}')
        self.assertEqual(response.status_code,200,response.data)
        self.assertIn('/photos/1/thumb/',response.data['products'][0]['thumbnail_url'])
        self.assertNotIn('cost_price',response.data['products'][0])
        self.assertEqual(self.client.get(self.photo()).status_code,200)
        self.assertEqual(self.save(files={'photo_2':picture()}).status_code,403)
        from sales.models import Sale,SaleItem
        sale=Sale.objects.create(store=self.store,created_by=self.user)
        SaleItem.objects.create(sale=sale,product=self.product,quantity=1,unit_price=120)
        response=self.client.get(f'/api/me/sales/{sale.pk}/?store_id={self.store.pk}')
        self.assertEqual(response.status_code,200,response.data)
        self.assertIn('/photos/1/thumb/',response.data['items'][0]['thumbnail_url'])
        self.assertEqual(response.data['total'],'120.00')

    def test_purchase_options_and_items_show_photo_without_product_view_permission(self):
        self.upload();self.user.user_permissions.clear()
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label='purchases',codename__in=['view_purchase','add_purchase']))
        response=self.client.get(f'/api/me/purchases/options/?store_id={self.store.pk}')
        self.assertEqual(response.status_code,200,response.data)
        self.assertIn('/photos/1/thumb/',response.data['products'][0]['thumbnail_url'])
        self.assertEqual(self.client.get(self.photo()).status_code,200)
        from .models import Supplier
        from purchases.models import Purchase,PurchaseItem
        supplier=Supplier(store=self.store,name='Fornecedor',created_by=self.user,updated_by=self.user);supplier.save(_service=True)
        purchase=Purchase(store=self.store,supplier=supplier,created_by=self.user,updated_by=self.user);purchase.save(_service=True)
        item=PurchaseItem(purchase=purchase,product=self.product,product_code=self.product.internal_code,product_name=self.product.name,quantity=1,unit_cost=50);item.save(_service=True)
        response=self.client.get(f'/api/me/purchases/{purchase.pk}/?store_id={self.store.pk}')
        self.assertEqual(response.status_code,200,response.data)
        self.assertIn('/photos/1/thumb/',response.data['items'][0]['thumbnail_url'])

    def test_inactivating_product_preserves_photos_for_existing_items(self):
        self.upload()
        self.assertEqual(self.client.delete(self.url()).status_code,204)
        self.assertTrue(ProductPhoto.objects.exists())
        self.assertEqual(self.client.get(self.photo()).status_code,200)

    def test_database_rejects_fourth_and_duplicate_slot(self):
        self.upload()
        asset=ProductPhotoAsset.objects.create(store=self.store,company_id_snapshot=self.company.pk,storage='local')
        for slot in (1,4):
            with self.assertRaises(IntegrityError),transaction.atomic():ProductPhoto.objects.create(product=self.product,asset=asset,slot=slot)

    @override_settings(DEBUG=False,PRODUCT_PHOTO_STORAGE='r2',LENTIS_R2_ENDPOINT='',LENTIS_R2_BUCKET='')
    def test_missing_cloud_config_blocks_only_photo_upload_not_normal_product_save(self):
        response=self.save(files={'photo_1':picture()},name='Não salvar')
        self.assertEqual(response.status_code,503,response.data)
        response=self.client.patch(self.url(),{'name':'Sem foto'},format='json')
        self.assertEqual(response.status_code,200,response.data)

    @override_settings(DEBUG=False,PRODUCT_PHOTO_STORAGE='local')
    def test_local_storage_is_never_accepted_in_production(self):
        with self.assertRaises(ImproperlyConfigured):PhotoStorage()


@override_settings(DEBUG=False,PRODUCT_PHOTO_STORAGE='r2',LENTIS_R2_ENDPOINT='https://'+'a'*32+'.r2.cloudflarestorage.com',
    LENTIS_R2_BUCKET='lentis-photos-test',LENTIS_R2_ACCESS_KEY_ID='unit-test-key',LENTIS_R2_SECRET_ACCESS_KEY='unit-test-secret')
class R2PhotoStorageTests(TestCase):
    def test_client_uses_explicit_r2_credentials_endpoint_and_short_timeouts(self):
        with patch('boto3.client') as client:r2_client()
        options=client.call_args.kwargs
        self.assertEqual(options['endpoint_url'],'https://'+'a'*32+'.r2.cloudflarestorage.com')
        self.assertEqual(options['region_name'],'auto')
        self.assertEqual(options['config'].connect_timeout,4)
        self.assertEqual(options['aws_access_key_id'],'unit-test-key')

    def test_upload_is_private_and_download_bounded_and_closed(self):
        client=Mock();body=Mock();body.read.return_value=b'JPEG';client.get_object.return_value={'Body':body}
        with patch('organizations.product_photo_storage.r2_client',return_value=client):
            storage=PhotoStorage();storage.put('key/image.jpg',b'JPEG')
            self.assertEqual(storage.get('key/thumb.jpg','thumb'),b'JPEG')
            storage.delete('key/image.jpg')
        client.put_object.assert_called_once_with(Bucket='lentis-photos-test',Key='key/image.jpg',Body=b'JPEG',ContentType='image/jpeg',CacheControl='private, no-store')
        body.read.assert_called_once_with(96*1024+1);body.close.assert_called_once()
        client.delete_object.assert_called_once_with(Bucket='lentis-photos-test',Key='key/image.jpg')

    def test_invalid_endpoint_does_not_send_credentials(self):
        for endpoint in ('http://localhost','https://example.com','https://'+'a'*32+'.r2.cloudflarestorage.com/path'):
            with override_settings(LENTIS_R2_ENDPOINT=endpoint),patch('boto3.client') as client:
                with self.assertRaises(ImproperlyConfigured):r2_client()
                client.assert_not_called()


@skipUnless(connection.vendor=='postgresql','Concorrência exige bloqueios reais do PostgreSQL.')
@override_settings(DEBUG=True,PRODUCT_PHOTO_STORAGE='local')
class ProductPhotosConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.directory=TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        setting=override_settings(PRODUCT_PHOTO_LOCAL_ROOT=self.directory.name);setting.enable();self.addCleanup(setting.disable)
        self.company=Company.objects.create(name='Concurrent')
        self.store=Store.objects.create(company=self.company,code='C1',name='Matriz')
        self.product=Product.objects.create(store=self.store,internal_code='C1',name='Armação')
        self.users=[User.objects.create_superuser(username=f'concurrent-{i}',password='test') for i in range(2)]

    def test_two_edits_with_same_revision_keep_only_one_gallery(self):
        barrier=Barrier(2)
        normalized_photos=[normalize_product_photo(picture(color=color)) for color in ('red','blue')]
        def send(index):
            close_old_connections()
            try:
                client=APIClient();client.force_authenticate(User.objects.get(pk=self.users[index].pk))
                # Separar decodificadores evita que o limite de memória por processo masque o lock SQL.
                normalized=normalized_photos[index]
                barrier.wait(timeout=10)
                from .product_photo_services import save_catalog_product
                try:
                    save_catalog_product(instance=Product.objects.get(pk=self.product.pk),values={},gallery={'revision':0,'remove':[]},
                        uploads={1:normalized},actor=self.users[index],clean=lambda p:p.full_clean())
                    return 200
                except Exception as exc:
                    if getattr(exc,'status_code',None)==409:return 409
                    raise
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(send,range(2)))
        self.assertEqual(sorted(results),[200,409])
        self.assertEqual(ProductPhoto.objects.filter(product=self.product).count(),1)
        self.assertEqual(ProductPhotoAsset.objects.count(),1)


class ProductPhotoMigrationTests(TransactionTestCase):
    def test_existing_products_prices_stock_and_codes_survive_migration(self):
        from django.db.migrations.executor import MigrationExecutor
        previous = [('organizations','0011_configurationevent_alter_company_options_and_more')]
        current = [('organizations','0012_productphoto_productphotoasset_product_bridge_mm_and_more')]
        executor=MigrationExecutor(connection);executor.migrate(previous)
        try:
            apps=executor.loader.project_state(previous).apps
            company=apps.get_model('organizations','Company').objects.create(name='Ótica preservada')
            store=apps.get_model('organizations','Store').objects.create(company=company,code='MIGPHOTO',name='Matriz')
            product=apps.get_model('organizations','Product').objects.create(store=store,internal_code='MIG-1',barcode='1234',name='Armação antiga',brand='Marca antiga',cost_price='120.50',sale_price='349.90',stock_quantity='-2.500',minimum_stock='1')
            executor=MigrationExecutor(connection);executor.migrate(current)
            apps=executor.loader.project_state(current).apps
            migrated=apps.get_model('organizations','Product').objects.get(pk=product.pk)
            self.assertEqual(str(migrated.sale_price),'349.90')
            self.assertEqual(str(migrated.cost_price),'120.50')
            self.assertEqual(str(migrated.stock_quantity),'-2.500')
            self.assertEqual(migrated.internal_code,'MIG-1')
            self.assertEqual(migrated.barcode,'1234')
            self.assertEqual(migrated.brand,'Marca antiga')
            self.assertEqual(migrated.photos_revision,0)
            self.assertIsNone(migrated.primary_photo_slot)
            self.assertIsNone(migrated.lens_width_mm)
            self.assertEqual(migrated.model_reference,'')
            self.assertFalse(apps.get_model('organizations','ProductPhoto').objects.exists())
        finally:
            executor=MigrationExecutor(connection);executor.migrate(executor.loader.graph.leaf_nodes())
