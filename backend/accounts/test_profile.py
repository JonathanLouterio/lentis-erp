from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from io import BytesIO
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from PIL import Image
from rest_framework.test import APIClient

from .profile_images import MAX_UPLOAD_BYTES, MAX_AVATAR_BYTES, normalize_avatar
from .profile_models import UserProfile
from .user_management_api import serialize as administrative_output

User = get_user_model()
URL = '/api/me/profile/'
AVATAR = URL+'avatar/'


def picture(fmt='PNG', size=(300, 200), color='purple', **options):
    stream = BytesIO()
    image = Image.new('RGB', size, color)
    image.save(stream, format=fmt, **options)
    return SimpleUploadedFile('foto.'+fmt.lower(), stream.getvalue(), content_type='image/'+fmt.lower())


class MyProfileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='personal-user', password='test-password', first_name='João', email='original@example.com')
        cls.other = User.objects.create_user(username='other-person', password='other-password', first_name='Outra pessoa')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def read(self):
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def update(self, *, version=None, format='json', **values):
        data = {'version':version or self.read()['version'], **values}
        return self.client.patch(URL, data, format=format)

    def test_profile_without_units_or_operational_permissions_is_available(self):
        data = self.read()
        self.assertEqual(data['username'], self.user.username)
        self.assertEqual(data['phone'], '')
        self.assertIsNone(data['avatar_url'])
        self.assertFalse(UserProfile.objects.exists())
        self.assertEqual(self.client.get('/api/me/stores/').data, [])

    def test_anonymous_cannot_read_write_or_download_photo(self):
        self.client.force_authenticate(None)
        for method, path in [('get',URL),('patch',URL),('get',AVATAR)]:
            with self.subTest(method=method):self.assertEqual(getattr(self.client,method)(path).status_code,403)

    def test_fresh_inactive_account_is_denied(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.client.get(URL).status_code,403)
        self.assertEqual(self.client.get(AVATAR).status_code,403)
        self.assertEqual(self.client.patch(URL,{},format='json').status_code,403)

    def test_csrf_is_required_for_json_and_multipart(self):
        client=APIClient(enforce_csrf_checks=True);client.force_login(self.user)
        version=client.get(URL).data['version']
        self.assertEqual(client.patch(URL,{'version':version,'first_name':'Sem CSRF'},format='json').status_code,403)
        self.assertEqual(client.patch(URL,{'version':version,'photo':picture()},format='multipart').status_code,403)
        token=client.get('/api/auth/csrf/').json()['csrfToken']
        response=client.patch(URL,{'version':version,'first_name':'Com CSRF'},format='multipart',HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code,200,response.data)

    def test_personal_fields_persist_and_normalize_contact(self):
        response=self.update(first_name='José',last_name='Louterio',email='contato@example.com',phone='(41) 99999-9999',whatsapp='+55 41 99999-9999',job_title='Atendimento',bio='Olá!\nCuido dos clientes.')
        self.assertEqual(response.status_code,200,response.data)
        data=self.read()
        self.assertEqual(data['phone'],'41999999999')
        self.assertEqual(data['whatsapp'],'5541999999999')
        self.assertEqual(data['bio'],'Olá!\nCuido dos clientes.')
        self.user.refresh_from_db();self.assertEqual(self.user.first_name,'José')
        self.assertEqual(self.user.email,'contato@example.com')
        self.assertEqual(self.client.get('/api/me/').data['first_name'],'José')

    def test_empty_optional_fields_are_supported(self):
        response=self.update(first_name='',last_name='',email='',phone='',whatsapp='',job_title='',bio='')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(self.read()['username'],self.user.username)

    def test_invalid_contact_and_lengths_do_not_write(self):
        cases=[{'email':'invalid'},{'phone':'a phone'},{'whatsapp':'123'},{'job_title':'x'*81},{'bio':'x'*501},{'first_name':'x'*151}]
        for values in cases:
            with self.subTest(values=values):self.assertEqual(self.update(**values).status_code,400)
        self.assertFalse(UserProfile.objects.exists())
        self.user.refresh_from_db();self.assertEqual(self.user.first_name,'João')

    def test_identity_access_and_theme_cannot_be_forged(self):
        for values in [{'id':self.other.pk},{'user_id':self.other.pk},{'username':'changed'},{'is_superuser':True},{'is_staff':True},{'is_active':False},{'permission_ids':[]},{'memberships':[]},{'theme':'dark'},{'password':'new-password'}]:
            with self.subTest(values=values):self.assertEqual(self.update(**values).status_code,400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username,'personal-user')
        self.assertTrue(self.user.check_password('test-password'))
        self.assertFalse(self.user.is_superuser)
        self.assertEqual(self.user.theme,'system')

    def test_multipart_also_rejects_unknown_fields(self):
        self.assertEqual(self.update(format='multipart',user_id=self.other.pk,photo=picture()).status_code,400)
        self.assertFalse(UserProfile.objects.exists())

    def test_queries_or_guessed_routes_cannot_target_another_user(self):
        UserProfile.objects.create(user=self.other,phone='41999999999')
        response=self.client.get(URL,{'user_id':self.other.pk})
        self.assertEqual(response.data['id'],self.user.pk)
        self.assertEqual(response.data['phone'],'')
        self.assertEqual(self.client.get(f'{URL}{self.other.pk}/').status_code,404)

    def test_each_user_keeps_separate_data_and_photo(self):
        own=self.update(format='multipart',photo=picture(color='red'),bio='Minha apresentação')
        self.assertEqual(own.status_code,200,own.data)
        own_photo=self.client.get(AVATAR).content
        self.client.force_authenticate(self.other)
        self.assertEqual(self.read()['bio'],'')
        self.assertEqual(self.client.get(AVATAR).status_code,404)
        response=self.update(format='multipart',photo=picture(color='blue'),bio='Outro perfil')
        self.assertEqual(response.status_code,200,response.data)
        self.assertNotEqual(self.client.get(AVATAR,{'user_id':self.user.pk}).content,own_photo)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.read()['bio'],'Minha apresentação')
        self.assertEqual(self.client.get(AVATAR).content,own_photo)

    def test_stale_version_rejects_all_fields_atomically(self):
        version=self.read()['version']
        self.assertEqual(self.update(version=version,first_name='Primeira').status_code,200)
        response=self.update(version=version,first_name='Segunda',bio='Não gravar')
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.read()['first_name'],'Primeira')
        self.assertEqual(self.read()['bio'],'')

    def test_administrative_identity_edit_invalidates_open_profile(self):
        version=self.read()['version']
        User.objects.filter(pk=self.user.pk).update(first_name='Alterado pelo administrador')
        response=self.update(version=version,first_name='Antigo',bio='Não persistir')
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.read()['first_name'],'Alterado pelo administrador')
        self.assertFalse(UserProfile.objects.exists())

    def test_personal_identity_edit_invalidates_admin_form(self):
        previous=administrative_output(self.user)['version']
        self.assertEqual(self.update(first_name='Nova identidade').status_code,200)
        self.user.refresh_from_db()
        self.assertNotEqual(administrative_output(self.user)['version'],previous)

    def test_theme_and_permissions_survive_personal_update(self):
        User.objects.filter(pk=self.user.pk).update(theme='dark')
        self.user.user_permissions.add(Permission.objects.get(content_type__app_label='organizations',codename='view_customer'))
        self.assertEqual(self.update(first_name='Mudou').status_code,200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.theme,'dark')
        self.assertTrue(self.user.has_perm('organizations.view_customer'))
        self.assertFalse(self.user.is_superuser)

    def test_session_survives_personal_update(self):
        client=APIClient();client.force_login(self.user)
        version=client.get(URL).data['version']
        self.assertEqual(client.patch(URL,{'version':version,'last_name':'Atualizado'},format='json').status_code,200)
        self.assertEqual(client.get('/api/me/').status_code,200)
        self.assertEqual(client.get(URL).data['last_name'],'Atualizado')

    def test_missing_version_and_unsupported_methods_are_rejected(self):
        self.assertEqual(self.client.patch(URL,{'bio':'Sem versão'},format='json').status_code,400)
        self.assertEqual(self.client.post(URL,{},format='json').status_code,405)
        self.assertEqual(self.client.delete(URL).status_code,405)
        self.assertEqual(self.client.post(AVATAR,{},format='json').status_code,405)

    def test_photo_is_private_bounded_jpeg(self):
        response=self.update(format='multipart',photo=picture('PNG',(600,300)))
        self.assertEqual(response.status_code,200,response.data)
        self.assertTrue(response.data['avatar_url'].startswith(AVATAR))
        download=self.client.get(response.data['avatar_url'])
        self.assertEqual(download.status_code,200)
        self.assertEqual(download['Content-Type'],'image/jpeg')
        self.assertEqual(download['X-Content-Type-Options'],'nosniff')
        self.assertIn('private',download['Cache-Control'])
        self.assertIn('no-store',download['Cache-Control'])
        self.assertEqual(download['Cross-Origin-Resource-Policy'],'same-origin')
        self.assertLessEqual(len(download.content),MAX_AVATAR_BYTES)
        with Image.open(BytesIO(download.content)) as image:
            self.assertEqual(image.size,(256,256));self.assertEqual(image.format,'JPEG')
        stored=UserProfile.objects.get(user=self.user)
        self.assertEqual(stored.avatar_sha256,sha256(download.content).hexdigest())

    def test_normalization_accepts_jpeg_png_and_webp(self):
        for fmt in ['JPEG','PNG','WEBP']:
            with self.subTest(fmt=fmt):self.assertEqual(self.update(format='multipart',photo=picture(fmt)).status_code,200)

    def test_original_filename_and_metadata_are_not_exposed(self):
        exif=Image.Exif();exif[270]='Private metadata';exif[274]=6
        photo=picture('JPEG',(300,400),exif=exif)
        photo.name='private-person-name.jpg'
        response=self.update(format='multipart',photo=photo)
        self.assertEqual(response.status_code,200,response.data)
        binary=self.client.get(AVATAR)
        self.assertEqual(binary['Content-Disposition'],'inline; filename="avatar.jpg"')
        with Image.open(BytesIO(binary.content)) as image:self.assertFalse(image.getexif())
        self.assertNotIn(b'Private metadata',binary.content)
        self.assertNotIn('private-person-name',str(response.data))

    def test_corrupt_svg_gif_and_disguised_files_do_not_overwrite_photo(self):
        self.assertEqual(self.update(format='multipart',photo=picture()).status_code,200)
        before=self.client.get(AVATAR).content
        bad=[b'<svg xmlns="http://www.w3.org/2000/svg"/>',b'<html>not a photograph</html>',picture('GIF').read(),b'\x89PNG\r\n\x1a\nBROKEN']
        for content in bad:
            response=self.update(format='multipart',photo=SimpleUploadedFile('disguised.jpg',content,content_type='image/jpeg'),first_name='Não salvar')
            self.assertEqual(response.status_code,400,response.data)
            self.assertEqual(self.client.get(AVATAR).content,before)
            self.assertEqual(self.read()['first_name'],'João')

    def test_animated_png_is_rejected(self):
        stream=BytesIO();frames=[Image.new('RGB',(16,16),color) for color in ['red','blue']]
        frames[0].save(stream,format='PNG',save_all=True,append_images=frames[1:],duration=100,loop=0)
        response=self.update(format='multipart',photo=SimpleUploadedFile('animated.png',stream.getvalue()))
        self.assertEqual(response.status_code,400,response.data)
        self.assertFalse(UserProfile.objects.exists())

    def test_large_pixel_dimensions_are_rejected_before_decode(self):
        photo=picture('PNG',(5000,3300))
        with patch('accounts.profile_images.ImageOps.exif_transpose') as transpose:
            response=self.update(format='multipart',photo=photo)
        self.assertEqual(response.status_code,400)
        transpose.assert_not_called()

    def test_upload_byte_limit_and_duplicate_files(self):
        oversized=SimpleUploadedFile('huge.jpg',b'0'*(MAX_UPLOAD_BYTES+1),content_type='image/jpeg')
        response=self.update(format='multipart',photo=oversized)
        self.assertEqual(response.status_code,413,response.data)
        response=self.update(format='multipart',photo=[picture(),picture()])
        self.assertEqual(response.status_code,413,response.data)
        self.assertFalse(UserProfile.objects.exists())

    def test_remove_photo_and_preserve_other_fields(self):
        self.assertEqual(self.update(format='multipart',photo=picture(),bio='Preservar').status_code,200)
        response=self.update(remove_avatar=True)
        self.assertEqual(response.status_code,200,response.data)
        self.assertIsNone(response.data['avatar_url'])
        self.assertEqual(self.client.get(AVATAR).status_code,404)
        stored=UserProfile.objects.get(user=self.user)
        self.assertEqual(bytes(stored.avatar),b'')
        self.assertEqual(self.read()['bio'],'Preservar')

    def test_photo_and_removal_cannot_be_requested_together(self):
        response=self.update(format='multipart',photo=picture(),remove_avatar=True)
        self.assertEqual(response.status_code,400,response.data)
        self.assertFalse(UserProfile.objects.exists())

    def test_text_edit_preserves_existing_photo(self):
        self.assertEqual(self.update(format='multipart',photo=picture()).status_code,200)
        previous=self.client.get(AVATAR).content
        self.assertEqual(self.update(bio='Texto').status_code,200)
        self.assertEqual(self.client.get(AVATAR).content,previous)

    def test_failure_does_not_partially_save_identity(self):
        with patch('accounts.profile_api.UserProfile.save',side_effect=RuntimeError('database failure')):
            with self.assertRaises(RuntimeError):self.update(first_name='Não persistir')
        self.user.refresh_from_db();self.assertEqual(self.user.first_name,'João')

    def test_read_and_error_responses_are_not_cached(self):
        self.assertIn('no-store',self.client.get(URL)['Cache-Control'])
        self.assertIn('no-store',self.update(version='x'*64)['Cache-Control'])
        self.assertIn('no-store',self.client.get(AVATAR)['Cache-Control'])


@skipUnless(connection.vendor=='postgresql','Concorrência exige bloqueios reais do PostgreSQL.')
class ProfileConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.user=User.objects.create_user(username='parallel-profile')
        client=APIClient();client.force_authenticate(self.user)
        self.version=client.get(URL).data['version']

    def test_two_profile_edits_reject_stale_version(self):
        barrier=Barrier(2)
        def edit(index):
            close_old_connections()
            try:
                client=APIClient();client.force_authenticate(User.objects.get(pk=self.user.pk))
                barrier.wait(timeout=10)
                return client.patch(URL,{'version':self.version,'first_name':f'Edição {index}'},format='json').status_code
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            tasks=[pool.submit(edit,index) for index in range(2)]
            results=[task.result(timeout=30) for task in tasks]
        self.assertEqual(sorted(results),[200,409])
        self.assertEqual(UserProfile.objects.filter(user=self.user).count(),1)
