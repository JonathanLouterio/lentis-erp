from django.db import migrations


class Migration(migrations.Migration):
    dependencies=[('sales','0010_alter_sale_options')]
    operations=[
        migrations.AlterModelOptions(name='cashsession',options={
            'verbose_name':'Abertura de caixa','verbose_name_plural':'Aberturas de caixa','ordering':['-opened_at','-pk'],
            'permissions':[('manage_cash','Pode operar e fechar caixas de outros responsáveis'),('move_cash','Pode registrar suprimento e retirada de caixa'),('close_cash','Pode fechar caixa')]}),
        migrations.AlterModelOptions(name='receivable',options={
            'verbose_name':'Parcela a receber','verbose_name_plural':'Parcelas a receber','ordering':['due_date','pk'],
            'permissions':[('receive_receivable','Pode registrar recebimento de parcela')]}),
    ]
