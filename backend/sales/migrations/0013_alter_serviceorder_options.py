from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [('sales', '0012_alter_quote_options')]
    operations = [migrations.AlterModelOptions(name='serviceorder', options={
        'ordering':['-pk'], 'verbose_name':'Ordem de serviço', 'verbose_name_plural':'Ordens de serviço',
        'permissions':[('advance_serviceorder','Pode avançar etapas da OS'),('rework_serviceorder','Pode registrar retrabalho da OS'),('cancel_serviceorder','Pode cancelar a OS')],
    })]
