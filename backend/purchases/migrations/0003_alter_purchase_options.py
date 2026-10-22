from django.db import migrations

class Migration(migrations.Migration):
    dependencies=[('purchases','0002_payableplan_payableinstallment_payablepayment_and_more')]
    operations=[migrations.AlterModelOptions(name='purchase',options={
        'verbose_name':'Compra', 'verbose_name_plural':'Compras', 'ordering':['-pk'],
        'permissions':[('receive_purchase','Confirmar entrada de compra'),('cancel_purchase','Cancelar rascunho de compra'),('update_purchase_cost','Atualizar custo cadastrado pela entrada de compra')],
    })]
