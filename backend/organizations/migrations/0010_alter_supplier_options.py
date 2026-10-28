from django.db import migrations

class Migration(migrations.Migration):
    dependencies=[('organizations','0009_alter_customer_options_alter_prescription_options')]
    operations=[migrations.AlterModelOptions(name='supplier',options={'verbose_name':'Fornecedor','verbose_name_plural':'Fornecedores','ordering':['name','pk'],
        'permissions':[('archive_supplier','Inativar fornecedor'),('restore_supplier','Reativar fornecedor')],
    })]
