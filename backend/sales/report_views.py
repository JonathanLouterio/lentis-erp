import csv
import io
from datetime import datetime
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from .insight_permissions import InsightPermission
from .models import FinancialAccount
from .views import SalesBaseView, SalesPagination
from .report_services import REPORTS, BUSINESS_TZ, available_reports, parse_filters, prepare_report, serialize_row

MAX_EXPORT_ROWS=20000


def csv_value(value,column):
    text=str(value or '')
    kind=column['kind']
    if kind=='money':return text.replace('.',',')
    if kind=='date':return '/'.join(reversed(text.split('-')))
    if kind=='datetime':return datetime.fromisoformat(text).astimezone(BUSINESS_TZ).strftime('%d/%m/%Y %H:%M:%S')
    # Campos livres nunca se tornam fórmulas ao abrir em uma planilha.
    if kind=='text' and (text.lstrip().startswith(('=','+','-','@')) or text.startswith(('\t','\r','\n'))):return "'"+text
    return text


class InsightReadView(SalesBaseView):
    permission_classes=[InsightPermission]
    def finalize_response(self,request,response,*args,**kwargs):
        response=super().finalize_response(request,response,*args,**kwargs)
        response['Cache-Control']='no-store, private'
        return response

class ReportOptionsView(InsightReadView):
    http_method_names=['get','head','options']
    def get(self,request):
        store=self._selected_store();now=timezone.now();today=timezone.localtime(now,BUSINESS_TZ).date()
        reports=available_reports(request.user)
        accounts=FinancialAccount.objects.filter(store=store) if any(r['key']=='movements' for r in reports) else []
        return Response({'can_export':request.user.has_perm('sales.export_reports'),'reports':reports,'accounts':[{'id':a.pk,'name':a.name,'is_active':a.is_active} for a in accounts],'timezone':str(BUSINESS_TZ),'start':today.replace(day=1).isoformat(),'end':today.isoformat(),'max_export_rows':MAX_EXPORT_ROWS},headers={'Cache-Control':'no-store, private'})


class ReportsView(InsightReadView):
    http_method_names=['get','head','options']
    def get(self,request):
        store=self._selected_store();now=timezone.now()
        values,today,lower,upper=parse_filters(request,store,now)
        query,columns,summary=prepare_report(store,values,now,today,lower,upper)
        kind=values['report'];spec=REPORTS[kind]
        if values.get('export')=='csv':
            limit_message=f'A exportação permite até {MAX_EXPORT_ROWS} linhas. Reduza o período ou refine os filtros; nenhum arquivo parcial foi gerado.'
            if query.count()>MAX_EXPORT_ROWS:
                raise ValidationError(limit_message)
            stream=io.StringIO(newline='');writer=csv.writer(stream,delimiter=';',lineterminator='\r\n')
            writer.writerow([c['label'] for c in columns])
            for index,obj in enumerate(query.iterator(chunk_size=1000)):
                if index>=MAX_EXPORT_ROWS:
                    raise ValidationError(limit_message)
                row=serialize_row(obj,kind,store,today)
                writer.writerow([csv_value(row.get(c['key'],''),c) for c in columns])
            response=HttpResponse('\ufeff'+stream.getvalue(),content_type='text/csv; charset=utf-8')
            response['Content-Disposition']=f'attachment; filename="lentis-{kind}-unidade-{store.pk}-{values["start"]}-{values["end"]}.csv"'
            response['Cache-Control']='no-store, private';response['X-Content-Type-Options']='nosniff'
            return response
        pagination=SalesPagination();rows=pagination.paginate_queryset(query,request,view=self)
        response=pagination.get_paginated_response([serialize_row(obj,kind,store,today) for obj in rows])
        response.data.update(title=spec['title'],description=spec['description'],basis=spec['basis'],columns=columns,summary=summary,generated_at=now.isoformat(),today=today.isoformat(),timezone=str(BUSINESS_TZ),store_id=store.pk,
            filters={'report':kind,'start':values['start'].isoformat(),'end':values['end'].isoformat(),'status':values['status'] if kind in ('receivables','payables') else 'all','debtor':values['debtor'] if kind=='receivables' else 'all','direction':values['direction'] if kind=='movements' else 'all','account_id':values.get('account_id') if kind=='movements' else None})
        response['Cache-Control']='no-store, private'
        return response
