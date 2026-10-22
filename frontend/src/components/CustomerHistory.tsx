import { useQuoteAccess } from '../hooks/useQuoteAccess'
import { useEffect, useState } from 'react'
import { getCustomerHistorySummary, getCustomerHistoryRecords, getCustomerHistoryRecord } from '../api'
import type { AccessibleStore, CashPage, CustomerHistorySummary, CustomerHistoryRecord, CustomerHistorySection } from '../api'
import { dateTime, money, failure } from './saleMoney'
import './CustomerHistory.css'

type Props = {store:AccessibleStore;customerId:number;onBack:()=>void;onSale:(id:number)=>void;onOrder:(saleId:number)=>void}
const tabs:Record<CustomerHistorySection,string>={sales:'Vendas',quotes:'Orçamentos',prescriptions:'Receitas',orders:'Ordens de serviço',installments:'Parcelas'}
const emptyPage:CashPage<CustomerHistoryRecord>={count:0,next:null,previous:null,results:[]}
function dateOnly(value:string){return value.split('-').reverse().join('/')}

export default function CustomerHistory({store,customerId,onBack,onSale,onOrder}:Props){
  const [summary,setSummary]=useState<CustomerHistorySummary|null>(null)
  const [section,setSection]=useState<CustomerHistorySection>('sales')
  const [page,setPage]=useState(1)
  const [records,setRecords]=useState(emptyPage)
  const [detail,setDetail]=useState<CustomerHistoryRecord|null>(null)
  const [loading,setLoading]=useState(true)
  const [loadingSummary,setLoadingSummary]=useState(true)
  const [loadingDetail,setLoadingDetail]=useState(false)
  const [error,setError]=useState('')
  const [summaryError,setSummaryError]=useState('')
  const [reload,setReload]=useState(0)
  const [detailId,setDetailId]=useState<number|null>(null)
  const quoteRights=useQuoteAccess(store.id,reload)
  const canQuotes=!!summary?.permissions.quotes && !!quoteRights.access?.actions.view

  useEffect(()=>{
    let ignore=false
    setLoadingSummary(true);setSummary(null);setSummaryError('')
    void getCustomerHistorySummary(store.id,customerId).then(v=>{if(!ignore)setSummary(v)}).catch(e=>{if(!ignore)setSummaryError(failure(e))}).finally(()=>{if(!ignore)setLoadingSummary(false)})
    return()=>{ignore=true}
  },[store.id,customerId,reload])
  useEffect(()=>{
    let ignore=false
    setRecords(emptyPage);setDetail(null);setDetailId(null);setError('');setLoading(true)
    if(!summary){setLoading(false);return()=>{ignore=true}}
    const restricted=(section==='quotes'&&!canQuotes)||(section==='prescriptions'&&!summary.permissions.prescriptions)||(section==='orders'&&!summary.permissions.orders)
    if(restricted){setError('Você não tem permissão para esta seção.');setLoading(false);return()=>{ignore=true}}
    void getCustomerHistoryRecords(store.id,customerId,section,page).then(v=>{if(!ignore)setRecords(v)}).catch(e=>{if(!ignore)setError(failure(e))}).finally(()=>{if(!ignore)setLoading(false)})
    return()=>{ignore=true}
  },[store.id,customerId,section,page,summary,canQuotes])
  useEffect(()=>{
    let ignore=false
    setDetail(null);setLoadingDetail(false)
    if(detailId===null || (section==='quotes'&&!canQuotes))return()=>{ignore=true}
    setLoadingDetail(true);setError('')
    void getCustomerHistoryRecord(store.id,customerId,section,detailId).then(v=>{if(!ignore)setDetail(v)}).catch(e=>{if(!ignore)setError(failure(e))}).finally(()=>{if(!ignore)setLoadingDetail(false)})
    return()=>{ignore=true}
  },[store.id,customerId,section,detailId,reload,canQuotes])
  const customer=summary?.customer
  const address=customer?[customer.street,customer.address_number,customer.address_complement,customer.neighborhood,customer.city,customer.state,customer.zip_code].filter(Boolean).join(' · '):''

  return <section className="customer-history">
    <header className="ch-heading"><div><span className="erp-kicker">CLIENTES · {store.name}</span><h1>Histórico do cliente</h1><p>Atendimentos e pendências reunidos por unidade.</p></div><div className="ch-buttons"><button type="button" className="erp-secondary-button" onClick={onBack}>Voltar aos clientes</button><button type="button" className="erp-secondary-button" onClick={()=>setReload(v=>v+1)} disabled={loadingSummary}>Atualizar histórico</button></div></header>
    {loadingSummary?<p role="status">Carregando histórico…</p>:summaryError?<p role="alert" className="erp-alert">{summaryError}</p>:customer&&summary?<>
      <div className="erp-card ch-customer"><div><h2>{customer.name}</h2><p>{customer.person_type==='company'?'Pessoa jurídica':'Pessoa física'} · {customer.cpf||customer.cnpj||'Documento não informado'}{!customer.is_active?' · Cadastro inativo':''}</p><p>{[customer.phone,customer.whatsapp,customer.email].filter(Boolean).join(' · ')||'Contato não informado'}</p>{address&&<p>{address}</p>}</div><small>Atualizado em {dateTime.format(new Date(summary.generated_at))}</small></div>
      <div className="ch-metrics"><div className="erp-card"><span>Vendas finalizadas</span><strong>{summary.summary.completed_sales}</strong><small>{summary.summary.draft_sales} rascunho(s)</small></div><div className="erp-card"><span>Saldo a receber do cliente</span><strong>{money.format(Number(summary.summary.customer_pending))}</strong><small>Vencido: {money.format(Number(summary.summary.customer_overdue))}</small></div><div className="erp-card"><span>A receber da operadora</span><strong>{money.format(Number(summary.summary.operator_pending))}</strong><small>Não é uma dívida do cliente.</small></div></div>
      <nav className="ch-tabs" aria-label="Seções do histórico">{(Object.keys(tabs) as CustomerHistorySection[]).map(key=><button type="button" key={key} className={section===key?'is-current':''} aria-pressed={section===key} disabled={key==='quotes'&&!canQuotes||key==='prescriptions'&&!summary.permissions.prescriptions||key==='orders'&&!summary.permissions.orders} onClick={()=>{setSection(key);setPage(1)}}>{tabs[key]}{key==='quotes'&&canQuotes&&summary.summary.quotes!==null?` (${summary.summary.quotes})`:key==='prescriptions'&&summary.summary.prescriptions!==null?` (${summary.summary.prescriptions})`:key==='orders'&&summary.summary.orders!==null?` (${summary.summary.orders})`:''}</button>)}</nav>
      {(!canQuotes||!summary.permissions.prescriptions||!summary.permissions.orders)&&<p className="ch-hint">Algumas seções exigem permissões específicas do usuário.</p>}
      {error&&<p role="alert" className="erp-alert">{error}</p>}
      {section==='installments'&&<p className="ch-hint">Parcelas do cliente e da operadora são identificadas separadamente. Vendas canceladas não compõem o saldo pendente.</p>}
      <div className="ch-grid"><div className="erp-card"><h2>{tabs[section]} <small>({records.count})</small></h2>{loading?<p role="status">Carregando registros…</p>:records.results.length===0?<p>Nenhum registro nesta seção.</p>:records.results.map(r=><button type="button" key={r.id} className={`ch-record${detailId===r.id?' is-selected':''}`} onClick={()=>setDetailId(r.id)} aria-label={`Detalhes de ${r.title}`}><span><strong>{r.title}</strong><small>{dateTime.format(new Date(r.date))}</small></span><span className="ch-status">{r.status_label}</span>{r.amount!==null&&<strong>{money.format(Number(r.amount))}</strong>}{r.remaining!==undefined&&<small>Saldo {money.format(Number(r.remaining))} · Vencimento {r.due_date?dateOnly(r.due_date):'—'} · {r.debtor==='operator'?'Operadora':'Cliente'}{r.overdue?' · Em atraso':''}</small>}</button>)}<div className="ch-pagination"><button type="button" disabled={loading||!records.previous} onClick={()=>setPage(v=>v-1)}>Anterior</button><span>Página {page}</span><button type="button" disabled={loading||!records.next} onClick={()=>setPage(v=>v+1)}>Próxima</button></div></div>
      <div className="erp-card ch-detail">{loadingDetail?<p role="status">Carregando detalhes…</p>:!detail?<><h2>Detalhes do registro</h2><p>Escolha um registro da lista para consultar.</p></>:<><div className="ch-detail-title"><h2>{detail.title}</h2><button type="button" aria-label="Fechar detalhes" onClick={()=>setDetailId(null)}>Fechar</button></div><p>{detail.status_label} · {dateTime.format(new Date(detail.date))}</p>{detail.amount!==null&&<strong>{money.format(Number(detail.amount))}</strong>}
        <dl className="ch-fields">{detail.fields.filter(f=>f.value).map((f,i)=><div key={i}><dt>{f.label}</dt><dd>{f.value}</dd></div>)}</dl>
        {detail.items.length>0&&<><h3>Itens registrados</h3><div className="ch-table"><table><thead><tr><th>Item</th><th>Quantidade</th><th>Total</th></tr></thead><tbody>{detail.items.map((item,i)=><tr key={i}><td>{item.code} · {item.name}</td><td>{item.quantity}</td><td>{item.total===null?'—':money.format(Number(item.total))}</td></tr>)}</tbody></table></div></>}
        {detail.clinical&&<><h3>Receita atual · versão do cadastro</h3><div className="ch-table"><table><thead><tr><th>Olho</th><th>Esférico</th><th>Cilíndrico</th><th>Eixo</th><th>Adição</th><th>DNP</th></tr></thead><tbody>{(['od','oe'] as const).map(eye=><tr key={eye}><th>{eye.toUpperCase()}</th>{(['sphere','cylinder','axis','addition','dnp'] as const).map(field=><td key={field}>{String(detail.clinical?.[`${eye}_${field}`]??'—')}</td>)}</tr>)}</tbody></table></div><p>DP: {detail.clinical.pd??'—'}</p><p className="ch-hint">As cópias usadas em vendas e OS são preservadas separadamente. Consulte-as no atendimento correspondente.</p></>}
        <div className="ch-buttons">{detail.sale_id&&<button type="button" className="erp-action-button" onClick={()=>onSale(detail.sale_id!)}>Abrir venda #{detail.sale_id}</button>}{detail.kind==='orders'&&detail.sale_id&&<button type="button" className="erp-secondary-button" onClick={()=>onOrder(detail.sale_id!)}>Acompanhar OS</button>}</div>
      </>}</div></div>
    </>:null}
  </section>
}
