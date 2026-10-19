from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from organizations.models import Prescription
from organizations.prescription_api import snapshot
from .prescription_models import SalePrescription


def can_view_prescriptions(user):
    return bool(user.is_active and user.has_perm('organizations.view_prescription'))


def apply_prescription(sale, user, selection):
    """Chamado dentro da transação do checkout e com o lock da venda mantido."""
    if selection is None:return False
    user=get_user_model().objects.get(pk=user.pk)
    if not can_view_prescriptions(user):raise PermissionDenied('É necessário ter permissão de visualizar receitas para escolher ou remover uma receita da venda.')
    if sale.status!='draft':raise ValidationError('A receita só pode ser escolhida enquanto a venda é um rascunho.')
    if selection.get('expected_record_id') != sale.prescription_record_id:
        raise ValidationError('O vínculo de receita foi alterado. Reabra a venda antes de selecionar novamente.')
    source_id=selection['prescription_id']
    previous=sale.prescription_record
    if source_id is None:
        if previous:
            SalePrescription.objects.create(sale=sale,customer=previous.customer,action='removed',snapshot={},created_by=user)
            sale.prescription_record=None
            return True
        return False
    if not sale.customer_id:raise ValidationError('Identifique o cliente antes de escolher uma receita.')
    source=Prescription.objects.select_for_update().filter(pk=source_id,store_id=sale.store_id,customer_id=sale.customer_id,is_active=True).first()
    if source is None:raise ValidationError('Selecione uma receita ativa do cliente e da unidade da venda.')
    if source.version!=selection.get('version'):raise ValidationError('A receita foi corrigida ou arquivada. Atualize as opções e confira a versão antes de salvar.')
    if previous and previous.source_id==source.pk and previous.source_version==source.version:return False
    sale.prescription_record=SalePrescription.objects.create(sale=sale,customer=source.customer,source=source,source_version=source.version,action='attached',snapshot={**snapshot(source),'customer_name':source.customer.name},created_by=user)
    return True


def prescription_output(record, *, include_snapshot=True):
    if record is None:return None
    return {'id':record.pk,'source_id':record.source_id,'source_version':record.source_version,'customer':record.customer_id,'action':record.action,**({'snapshot':record.snapshot} if include_snapshot else {}),'creator_username':record.created_by.username,'created_at':record.created_at}
