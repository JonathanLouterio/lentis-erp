import { useEffect, useState } from 'react'
import { getAgendaDay } from '../api'
import type { AgendaDay, AgendaTarget } from '../api'
import FormDialog from './FormDialog'
import { displayDate, failure, money } from './saleMoney'

export default function AgendaDayDialog({storeId,storeName,date,onClose,onOpenTarget}:{
  storeId:number;storeName:string;date:string;onClose:()=>void;onOpenTarget:(target:AgendaTarget)=>void
}){
  const [page,setPage]=useState(1)
  const [reload,setReload]=useState(0)
  const [loading,setLoading]=useState(true)
  const [data,setData]=useState<AgendaDay|null>(null)
  const [error,setError]=useState('')
  useEffect(()=>{
    let active=true
    setLoading(true);setData(null);setError('')
    void getAgendaDay(storeId,date,page).then(value=>{if(active)setData(value)})
      .catch(error=>{if(active)setError(failure(error))}).finally(()=>{if(active)setLoading(false)})
    return ()=>{active=false}
  },[storeId,date,page,reload])
  return <FormDialog wide title={`Compromissos de ${displayDate(date)}`} subtitle={storeName}
    sectionLabel="GESTÃO · AGENDA FINANCEIRA" onClose={onClose}>
    <p>Parcelas ainda em aberto neste vencimento. Abra o lançamento para consultar os dados atuais.</p>
    {error&&<div role="alert" className="erp-alert"><p>{error}</p><button type="button" onClick={()=>setReload(value=>value+1)}>Tentar novamente</button></div>}
    {loading&&<p role="status">Carregando compromissos…</p>}
    {data&&<>
      <dl className="agenda-day-summary">
        <div><dt>Entradas previstas</dt><dd>{money.format(Number(data.incoming))}</dd></div>
        <div><dt>Saídas previstas</dt><dd>{money.format(Number(data.outgoing))}</dd></div>
        <div><dt>Diferença prevista</dt><dd>{money.format(Number(data.net))}</dd></div>
      </dl>
      <p>{data.count} parcela(s) em aberto. Os totais incluem todas as páginas deste dia.</p>
      <ul className="agenda-day-list" aria-label="Compromissos do dia" role="list">
        {data.results.map(row=><li key={row.row_id}>
          <div className="agenda-day-heading"><strong>{row.party}</strong><span>{row.direction} · {row.group}</span></div>
          <p>{row.document} · Parcela {row.number}</p>
          <dl>
            <div><dt>Valor original</dt><dd>{money.format(Number(row.original))}</dd></div>
            <div><dt>Já baixado</dt><dd>{money.format(Number(row.settled_amount))}</dd></div>
            <div><dt>Em aberto</dt><dd>{money.format(Number(row.remaining_amount))}</dd></div>
          </dl>
          <button type="button" className="agenda-day-open"
            aria-label={'Abrir '+row.document+', parcela '+row.number+' em '+(row.direction==='Entrada'?'Recebimentos':'Contas a pagar')}
            onClick={()=>onOpenTarget(row.direction==='Entrada'
              ? {kind:'receivable',id:row.target_id}
              : {kind:'payable',id:row.target_id,installmentId:row.installment_id})}>
            {row.direction==='Entrada'?'Abrir em Recebimentos':'Abrir em Contas a pagar'}
          </button>
        </li>)}
      </ul>
      {!data.count&&<p>Nenhum compromisso em aberto neste vencimento. A parcela pode ter sido quitada desde a última consulta.</p>}
      <div className="report-pagination">
        <button type="button" disabled={loading||!data.previous} onClick={()=>setPage(value=>value-1)}>Anterior</button>
        <span>Página {page}</span>
        <button type="button" disabled={loading||!data.next} onClick={()=>setPage(value=>value+1)}>Próxima</button>
      </div>
    </>}
  </FormDialog>
}
