from django.db import migrations

class Migration(migrations.Migration):
    dependencies=[('sales','0013_alter_serviceorder_options')]
    operations=[migrations.AlterModelOptions(name='sale',options={'verbose_name':'Venda','verbose_name_plural':'Vendas','ordering':['-created_at','-pk'],
        'permissions':[('finalize_sale','Pode confirmar venda'),('cancel_sale','Pode cancelar venda'),('view_dashboard','Consultar painel operacional'),('view_reports','Consultar relatórios gerenciais'),('export_reports','Exportar relatórios gerenciais')],
    })]
