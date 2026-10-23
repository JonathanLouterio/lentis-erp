from django.db import migrations

class Migration(migrations.Migration):
    dependencies=[('organizations','0008_supplier_supplierevent_supplieroperation_and_more')]
    operations=[
        migrations.AlterModelOptions(name='customer',options={'verbose_name':'Cliente','verbose_name_plural':'Clientes','ordering':['name'],'permissions':[('view_customer_history','Consultar histórico consolidado do cliente')]}),
        migrations.AlterModelOptions(name='prescription',options={'verbose_name':'Receita oftalmológica','verbose_name_plural':'Receitas oftalmológicas','ordering':['-issued_on','-pk'],'permissions':[('archive_prescription','Arquivar receita oftalmológica')]}),
    ]
