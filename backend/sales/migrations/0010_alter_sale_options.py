from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('sales', '0009_serviceorder_serviceorderevent_serviceorderoperation_and_more')]
    operations = [migrations.AlterModelOptions(name='sale', options={
        'verbose_name': 'Venda', 'verbose_name_plural': 'Vendas',
        'ordering': ['-created_at', '-pk'],
        'permissions': [('finalize_sale', 'Pode confirmar venda'), ('cancel_sale', 'Pode cancelar venda')],
    })]
