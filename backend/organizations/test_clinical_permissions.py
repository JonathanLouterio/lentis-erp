from uuid import uuid4
from django.contrib.auth.models import Permission,Group
from django.test import TestCase
from rest_framework.test import APIClient
from . import test_prescriptions as fixtures
from .models import Prescription,PrescriptionRevision,Customer
from sales.models import Sale
from sales.prescription_services import can_view_prescriptions

class ClinicalPermissionTests(TestCase):
    setUp=fixtures.PrescriptionAPITests.setUp
    grant=fixtures.PrescriptionAPITests.grant
    data=fixtures.PrescriptionAPITests.data
    write=fixtures.PrescriptionAPITests.write
    archive=fixtures.PrescriptionAPITests.archive

    def only(self,*codes):
        self.user.user_permissions.remove(*Permission.objects.filter(content_type__app_label='organizations'))
        self.grant(self.user,*codes)

    def rx_url(self,record=None):return f"/api/me/prescriptions/{str(record['id'])+'/' if record else ''}?store_id={self.store.pk}"
    def history_url(self,section='summary',**extra):
        query=''.join(f'&{k}={v}' for k,v in extra.items())
        return f'/api/me/customers/{self.customer.pk}/history/?store_id={self.store.pk}&section={section}{query}'
    def history_grant(self):self.grant(self.user,'view_customer','view_customer_history')

    def test_correction_does_not_authorize_archive(self):
        self.only('view_prescription','add_prescription','change_prescription');record=self.write()
        self.assertEqual(self.archive(record).status_code,403)
        corrected=self.write(self.data(expected_version=1,reason='Digitação',od_sphere='-1.50'),record)
        self.assertEqual(corrected['version'],2);self.assertEqual(PrescriptionRevision.objects.count(),2)

    def test_archiver_can_archive_without_correcting(self):
        self.grant();record=self.write();self.only('view_prescription','archive_prescription')
        self.write(self.data(expected_version=1,reason='Correção'),record,expected=403)
        result=self.archive(record);self.assertEqual(result.status_code,200,result.data)
        self.assertFalse(result.data['is_active']);self.assertEqual(PrescriptionRevision.objects.count(),2)

    def test_read_only_cannot_create_correct_or_archive(self):
        self.grant();record=self.write();self.only('view_prescription')
        self.assertEqual(self.client.get(self.rx_url(record)).status_code,200)
        self.write(expected=403);self.write(self.data(expected_version=1,reason='Altera'),record,expected=403)
        self.assertEqual(self.archive(record).status_code,403)

    def test_action_without_clinical_view_is_denied(self):
        self.only('add_prescription','change_prescription','archive_prescription')
        self.write(expected=403);self.assertEqual(self.client.get(self.rx_url()).status_code,403)
        self.assertEqual(self.client.get(f'/api/me/prescriptions/customers/?store_id={self.store.pk}').status_code,403)

    def test_minimal_customer_options_do_not_require_full_customer_read(self):
        self.only('view_prescription','add_prescription')
        Customer.objects.create(store=self.other,name='Cliente filial')
        Customer.objects.create(store=self.store,name='Inativo',is_active=False)
        response=self.client.get(f'/api/me/prescriptions/customers/?store_id={self.store.pk}')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['results'],[{'id':self.customer.pk,'name':self.customer.name}])
        self.assertEqual(self.client.get(f'/api/me/customers/?store_id={self.store.pk}').status_code,403)
        self.write()

    def test_revoked_view_blocks_list_detail_revisions_and_sale_copy_helper(self):
        self.grant();record=self.write();self.assertTrue(can_view_prescriptions(self.user))
        self.user.has_perm('organizations.view_prescription')
        self.user.user_permissions.remove(Permission.objects.get(content_type__app_label='organizations',codename='view_prescription'))
        self.assertFalse(can_view_prescriptions(self.user))
        self.assertEqual(self.client.get(self.rx_url()).status_code,403)
        self.assertEqual(self.client.get(self.rx_url(record)).status_code,403)
        self.assertEqual(self.client.get(f'/api/me/sales/prescription-access/?store_id={self.store.pk}').data['can_view'],False)

    def test_group_revocation_blocks_archive_retry(self):
        self.grant();record=self.write();self.only('view_prescription')
        group=Group.objects.create(name='Arquivo clínico');group.permissions.add(Permission.objects.get(content_type__app_label='organizations',codename='archive_prescription'));self.user.groups.add(group)
        payload={'request_id':str(uuid4()),'expected_version':1,'reason':'Duplicada'}
        self.assertEqual(self.archive(record,**payload).status_code,200)
        group.permissions.clear()
        self.assertEqual(self.archive(record,**payload).status_code,403)
        self.assertEqual(PrescriptionRevision.objects.count(),2)

    def test_revoked_create_cannot_replay(self):
        self.grant();data=self.data();self.write(data)
        self.user.user_permissions.remove(Permission.objects.get(content_type__app_label='organizations',codename='add_prescription'))
        self.write(data,expected=403);self.assertEqual(Prescription.objects.count(),1)

    def test_history_requires_both_customer_and_history_read(self):
        self.only('view_customer')
        self.assertEqual(self.client.get(self.history_url()).status_code,403)
        self.only('view_customer_history')
        self.assertEqual(self.client.get(self.history_url()).status_code,403)
        self.history_grant();self.assertEqual(self.client.get(self.history_url()).status_code,200)

    def test_history_masks_each_module_counts_and_financial_summary(self):
        self.user.user_permissions.clear();self.history_grant()
        Sale.objects.create(store=self.store,customer=self.customer,created_by=self.user)
        response=self.client.get(self.history_url());self.assertEqual(response.status_code,200,response.data)
        self.assertFalse(any(response.data['permissions'].values()))
        self.assertTrue(all(v is None for v in response.data['summary'].values()))
        for section in ('sales','quotes','orders','prescriptions','installments'):
            self.assertEqual(self.client.get(self.history_url(section)).status_code,403)
            self.assertEqual(self.client.get(self.history_url(section,record_id=1)).status_code,403)

    def test_history_finance_permission_does_not_grant_sales_or_clinical(self):
        self.user.user_permissions.clear();self.history_grant()
        self.user.user_permissions.add(Permission.objects.get(content_type__app_label='sales',codename='view_receivable'))
        response=self.client.get(self.history_url());self.assertEqual(response.status_code,200)
        self.assertIsNone(response.data['summary']['completed_sales']);self.assertIsNone(response.data['summary']['prescriptions'])
        self.assertEqual(response.data['summary']['customer_pending'],'0.00')
        self.assertEqual(self.client.get(self.history_url('installments')).status_code,200)
        self.assertEqual(self.client.get(self.history_url('sales')).status_code,403)

    def test_clinical_history_does_not_grant_sales_or_balances(self):
        self.grant();record=self.write();self.user.user_permissions.clear();self.history_grant();self.grant(self.user,'view_prescription')
        response=self.client.get(self.history_url());self.assertEqual(response.status_code,200)
        self.assertEqual(response.data['summary']['prescriptions'],1);self.assertIsNone(response.data['summary']['customer_pending'])
        detail=self.client.get(self.history_url('prescriptions',record_id=record['id']))
        self.assertEqual(detail.status_code,200);self.assertEqual(detail.data['clinical']['od_sphere'],'-1.25')
        self.assertEqual(self.client.get(self.history_url('sales')).status_code,403)

    def test_history_revocation_blocks_cached_actor_and_identity(self):
        self.history_grant();self.assertEqual(self.client.get(self.history_url()).status_code,200)
        self.user.has_perm('organizations.view_customer_history')
        self.user.user_permissions.remove(Permission.objects.get(content_type__app_label='organizations',codename='view_customer_history'))
        response=self.client.get(self.history_url());self.assertEqual(response.status_code,403)
        self.assertNotIn('customer',response.data)

    def test_rx_revocation_masks_history_count_and_detail(self):
        self.grant();record=self.write();self.history_grant()
        self.assertEqual(self.client.get(self.history_url()).data['summary']['prescriptions'],1)
        self.user.user_permissions.remove(Permission.objects.get(content_type__app_label='organizations',codename='view_prescription'))
        self.assertIsNone(self.client.get(self.history_url()).data['summary']['prescriptions'])
        self.assertEqual(self.client.get(self.history_url('prescriptions',record_id=record['id'])).status_code,403)

    def test_own_capabilities_and_scoping_are_private(self):
        self.grant();response=self.client.get(f'/api/me/clinical-access/?store_id={self.store.pk}')
        self.assertEqual(response.status_code,200);self.assertTrue(response.data['prescriptions']['view']);self.assertIn('no-store',response['Cache-Control'])
        self.assertIn(self.client.get(f'/api/me/clinical-access/?store_id={self.other.pk}').status_code,(400,403))
        self.assertNotIn('customers',response.data)

    def test_staff_and_inactive_accounts_do_not_bypass_clinical_rights(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(self.rx_url()).status_code,403)
        self.client.force_authenticate(self.user);self.grant()
        type(self.user).objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.client.get(self.rx_url()).status_code,403)
        self.assertFalse(can_view_prescriptions(self.user))

    def test_anonymous_and_archive_without_csrf_are_denied(self):
        self.grant();record=self.write();client=APIClient(enforce_csrf_checks=True)
        path=f"/api/me/prescriptions/{record['id']}/archive/?store_id={self.store.pk}"
        self.assertEqual(client.get(f'/api/me/clinical-access/?store_id={self.store.pk}').status_code,403)
        client.force_login(self.user)
        self.assertEqual(client.post(path,{'request_id':str(uuid4()),'expected_version':1,'reason':'Arquivo'},format='json').status_code,403)
        self.assertTrue(Prescription.objects.get().is_active)
