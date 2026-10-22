from django.db import migrations


class Migration(migrations.Migration):
    dependencies=[('sales','0011_alter_cashsession_options_alter_receivable_options')]
    operations=[migrations.AlterModelOptions(name='quote',options={
        'verbose_name':'Orçamento','verbose_name_plural':'Orçamentos','ordering':['-created_at','-pk'],
        'permissions':[('send_quote','Pode preparar proposta de orçamento'),('accept_quote','Pode registrar aceite de orçamento'),('reject_quote','Pode recusar orçamento'),('print_quote','Pode imprimir orçamento'),('convert_quote','Pode converter orçamento em venda')],
    })]
