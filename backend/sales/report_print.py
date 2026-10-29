"""HTML de impressão com todos os resultados, limitado antes de responder."""
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .dashboard_views import BUSINESS_TZ
from .report_services import serialize_row


def currency(value):
    from decimal import Decimal
    return 'R$ ' + f'{Decimal(value or 0):,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')


def print_receivables(query, columns, summary, values, store, now, today, limit, aging):
    if query.count()>limit:
        raise ValidationError(f'A impressão permite até {limit} parcelas. Refine os filtros; nenhum relatório parcial foi gerado.')
    # Colunas operacionais ficam na consulta/CSV. A impressão mantém o essencial para caber em A4 paisagem.
    keys=['document','number','party','debtor','due_date','amount','paid','remaining','risk_label','days_overdue']
    selected=[next(c for c in columns if c['key']==key) for key in keys]
    rows=[]
    for index,obj in enumerate(query.iterator(chunk_size=500)):
        if index>=limit:
            raise ValidationError(f'A impressão permite até {limit} parcelas. Refine os filtros.')
        row=serialize_row(obj,'receivables',store,today,values['warning_days'])
        cells=[]
        for col in selected:
            value=row[col['key']]
            if col['kind']=='money':value=currency(value)
            elif col['kind']=='date':value='/'.join(reversed(value.split('-')))
            cells.append({'value':value,'kind':col['kind']})
        rows.append({'tone':row['tone'],'cells':cells})
    status={'all':'Todas','pending':'Em aberto, incluindo parciais','paid':'Quitadas','partial':'Pagas parcialmente','overdue':'Vencidas'}
    debtor={'all':'Clientes e operadoras','customer':'Clientes','operator':'Operadoras de cartão'}
    from .receivable_report import RISK_LABELS,AGE_LABELS
    methods={'all':'Todas','cash':'Dinheiro','pix':'Pix','transfer':'Transferência','credit':'Cartão de crédito','debit':'Cartão de débito','boleto':'Boleto','store_credit':'Crediário'}
    filters=[('Vencimentos','Todos os vencimentos' if values['all_dates'] else f'{values["start"]:%d/%m/%Y} a {values["end"]:%d/%m/%Y}'),
        ('Situação',status[values['status']]),('Responsável',debtor[values['debtor']]),('Cliente',values['customer'] or 'Todos'),
        ('Venda',f'#{values["sale_id"]}' if values.get('sale_id') else 'Todas'),('Forma',methods[values['method']]),
        ('Prazo',RISK_LABELS.get(values['risk'],'Todos')),('Faixa',AGE_LABELS.get(values['aging'],'Todas')),
        ('Janela amarela',f'{values["warning_days"]} dias, incluindo hoje')]
    html=render_to_string('sales/receivable_report_print.html',{
        'store':store,'generated':timezone.localtime(now,BUSINESS_TZ).strftime('%d/%m/%Y %H:%M'),'today':today,'filters':filters,
        'summary':[{**m,'display':currency(m['value']) if m['kind']=='money' else m['value']} for m in summary],
        'aging':[{**item,'display':currency(item['amount'])} for item in aging], 'columns':selected, 'rows':rows,
    })
    response=HttpResponse(html,content_type='text/html; charset=utf-8')
    response['Cache-Control']='no-store, private'
    response['X-Content-Type-Options']='nosniff'
    response['Content-Security-Policy']="default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'"
    response['X-Frame-Options']='DENY'
    return response
