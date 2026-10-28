import { useInsightAccess } from '../hooks/useInsightAccess'
import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { getReport, getReportOptions, exportReport } from '../api'
import type { AccessibleStore, ReportColumn, ReportData, ReportFilters, ReportKind, ReportOptions } from '../api'
import { displayDate, failure, signedDecimal } from './saleMoney'
import './Reports.css'

type Props={store:AccessibleStore;onSavingChange:(value:boolean)=>void}
function currency(value:string){const cents=signedDecimal(value);if(cents===null)return '—';const amount=cents<0n?-cents:cents;return `${cents<0n?'− ':''}R$ ${new Intl.NumberFormat('pt-BR',{maximumFractionDigits:0}).format(amount/100n)},${(amount%100n).toString().padStart(2,'0')}`}
function defaults(report:ReportKind,start:string,end:string):ReportFilters{return {report,start,end,status:'pending',debtor:'all',direction:'all',account_id:null}}
function equal(a:ReportFilters|null,b:ReportFilters|null){return JSON.stringify(a)===JSON.stringify(b)}
function validDates(filters:ReportFilters|null){if(!filters?.start||!filters.end||filters.start>filters.end)return false;const days=(Date.parse(`${filters.end}T00:00:00Z`)-Date.parse(`${filters.start}T00:00:00Z`))/86400000;return Number.isFinite(days)&&days>=0&&days<=365}
function cell(value:string,column:ReportColumn,zone:string){if(value===undefined||value===null||value==='')return '—';if(column.kind==='money')return currency(value);if(column.kind==='date')return displayDate(value);if(column.kind==='datetime')return new Intl.DateTimeFormat('pt-BR',{dateStyle:'short',timeStyle:'short',timeZone:zone}).format(new Date(value));if(column.kind==='integer')return new Intl.NumberFormat('pt-BR',{maximumFractionDigits:0}).format(BigInt(value));return value}

export default function Reports({store,onSavingChange}:Props){
  const [options,setOptions]=useState<ReportOptions|null>(null)
  const [draft,setDraft]=useState<ReportFilters|null>(null)
  const [applied,setApplied]=useState<ReportFilters|null>(null)
  const [page,setPage]=useState(1)
  const [data,setData]=useState<ReportData|null>(null)
  const [loadingOptions,setLoadingOptions]=useState(true)
  const [loading,setLoading]=useState(false)
  const [exporting,setExporting]=useState(false)
  const [error,setError]=useState('')
  const [success,setSuccess]=useState('')
  const [reload,setReload]=useState(0)
  const [retryOptions,setRetryOptions]=useState(0)
  const rights=useInsightAccess(store.id,retryOptions)
  const rightsKey=JSON.stringify([rights.access?.reports,rights.access?.export])
  const anyReports=Object.values(rights.access?.reports||{}).some(Boolean)
  const changed=!equal(draft,applied)
  useEffect(()=>{onSavingChange(exporting);return()=>onSavingChange(false)},[exporting,onSavingChange])
  useEffect(()=>{if(!anyReports)return;let ignore=false;setLoadingOptions(true);setError('');setOptions(null);setData(null);setApplied(null);setDraft(null);void getReportOptions(store.id).then(value=>{if(ignore)return;setOptions(value);if(value.reports[0]){const initial=defaults(value.reports[0].key,value.start,value.end);setDraft(initial);setApplied(initial);setPage(1)}}).catch(e=>{if(!ignore)setError(failure(e))}).finally(()=>{if(!ignore)setLoadingOptions(false)});return()=>{ignore=true}},[store.id,retryOptions,rightsKey,anyReports])
  useEffect(()=>{if(!applied||!rights.access?.reports[applied.report])return;let ignore=false;setLoading(true);setError('');setData(null);void getReport(store.id,applied,page).then(value=>{if(!ignore)setData(value)}).catch(e=>{if(!ignore)setError(failure(e))}).finally(()=>{if(!ignore)setLoading(false)});return()=>{ignore=true}},[store.id,applied,page,reload,rightsKey])
  function changeKind(kind:ReportKind){if(!applied||exporting||!options?.reports.some(r=>r.key===kind))return;const next=defaults(kind,applied.start,applied.end);setDraft(next);setApplied(next);setPage(1);setSuccess('')}
  function change<K extends keyof ReportFilters>(key:K,value:ReportFilters[K]){if(!draft||exporting)return;setDraft({...draft,[key]:value});setSuccess('')}
  function period(preset:string){if(!draft||!options||!preset)return;const end=options.end;let start=end;if(preset==='month')start=end.slice(0,8)+'01';if(preset==='7days'){const date=new Date(`${end}T00:00:00Z`);date.setUTCDate(date.getUTCDate()-6);start=date.toISOString().slice(0,10)}setDraft({...draft,start,end});setSuccess('')}
  function apply(event:FormEvent){event.preventDefault();if(!draft||!validDates(draft)||exporting)return;setApplied({...draft});setPage(1);setSuccess('');setReload(value=>value+1)}
  async function download(){
    if(!applied||!rights.access?.export||!rights.access.reports[applied.report]||exporting||loading||changed||!data)return;setExporting(true);setError('');setSuccess('')
    try{const file=await exportReport(store.id,applied);const url=URL.createObjectURL(file.blob);const link=document.createElement('a');link.href=url;link.download=file.filename;document.body.appendChild(link);link.click();link.remove();window.setTimeout(()=>URL.revokeObjectURL(url),1000);setSuccess('CSV gerado com todos os resultados dos filtros aplicados.')}
    catch(e){setError(failure(e))}finally{setExporting(false)}
  }
  if(!anyReports)return <section className="erp-card"><h1>Relatórios gerenciais</h1><p>{rights.loading?'Conferindo acessos…':rights.error||'Seu usuário não tem permissão para consultar estes relatórios.'}</p></section>
  return <section className="report-page" aria-busy={loadingOptions||loading||exporting}>
    <header className="report-heading"><div><span className="erp-kicker">GESTÃO · {store.name}</span><h1>Relatórios gerenciais</h1><p>Consulte resultados e acompanhe os compromissos da unidade.</p></div><button hidden={!rights.access?.export} type="button" className="erp-action-button" disabled={!data||loading||exporting||changed} onClick={()=>void download()}>{exporting?'Gerando CSV…':'Exportar CSV'}</button></header>
    {error&&<p className="erp-alert" role="alert">{error}</p>}{success&&<p className="report-success" role="status">{success}</p>}
    {loadingOptions?<div className="erp-card" role="status">Carregando relatórios disponíveis…</div>:!options?<div className="erp-card"><button type="button" onClick={()=>setRetryOptions(v=>v+1)}>Tentar carregar relatórios novamente</button></div>:!options.reports.length?<div className="erp-card"><h2>Acesso aos relatórios</h2><p>Seu usuário não tem permissões de consulta para estes relatórios. Solicite as permissões necessárias ao administrador da unidade.</p></div>:<>
    <nav className="report-choices" aria-label="Tipos de relatório">{options.reports.map(report=><button type="button" key={report.key} disabled={exporting} aria-pressed={applied?.report===report.key} className={applied?.report===report.key?'is-active':''} onClick={()=>changeKind(report.key)}><strong>{report.title}</strong><span>{report.basis}</span></button>)}</nav>
    {draft&&<form className="erp-card report-filter-form" onSubmit={apply}><div className="report-filter-heading"><h2>Filtros da consulta</h2><label>Atalho de período<select aria-label="Atalho de período do relatório" value="" disabled={exporting} onChange={e=>period(e.target.value)}><option value="">Escolha um atalho</option><option value="today">Hoje</option><option value="7days">Últimos 7 dias</option><option value="month">Mês até hoje</option></select></label></div><fieldset disabled={exporting}><legend className="report-visually-hidden">Definir período e condições</legend><div className="report-fields"><label>Data inicial<input aria-label="Data inicial do relatório" type="date" value={draft.start} onChange={e=>change('start',e.target.value)} required/></label><label>Data final<input aria-label="Data final do relatório" type="date" value={draft.end} onChange={e=>change('end',e.target.value)} required/></label>
    {(draft.report==='receivables'||draft.report==='payables')&&<label>Situação atual<select aria-label="Situação das parcelas no relatório" value={draft.status} onChange={e=>change('status',e.target.value as ReportFilters['status'])}><option value="pending">Em aberto, incluindo parciais</option><option value="overdue">Vencidas</option><option value="paid">Quitadas</option><option value="all">Todas</option></select></label>}
    {draft.report==='receivables'&&<label>Responsável pelo pagamento<select aria-label="Responsável no relatório" value={draft.debtor} onChange={e=>change('debtor',e.target.value as ReportFilters['debtor'])}><option value="all">Clientes e operadoras</option><option value="customer">Clientes</option><option value="operator">Operadoras de cartão</option></select></label>}
    {draft.report==='movements'&&<><label>Direção<select aria-label="Direção dos movimentos no relatório" value={draft.direction} onChange={e=>change('direction',e.target.value as ReportFilters['direction'])}><option value="all">Entradas e saídas</option><option value="in">Entradas</option><option value="out">Saídas</option></select></label><label>Conta financeira<select aria-label="Conta no relatório" value={draft.account_id||''} onChange={e=>change('account_id',e.target.value?Number(e.target.value):null)}><option value="">Todas as contas</option>{options.accounts.map(a=><option key={a.id} value={a.id}>{a.name}{a.is_active?'':' · Inativa'}</option>)}</select></label></>}
    </div><div className="report-filter-footer"><span>Até 366 dias. Fuso: São Paulo.</span><button className="erp-action-button" type="submit" disabled={!validDates(draft)||loading}>Aplicar filtros</button></div></fieldset>{!validDates(draft)&&<p className="report-warning">Informe um período válido de até 366 dias.</p>}{changed&&<p className="report-warning" role="status">Filtros alterados. Clique em Aplicar filtros para atualizar os resultados e liberar a exportação.</p>}</form>}
    {loading?<div className="erp-card" role="status">Calculando o relatório da unidade…</div>:data&&rights.access?.reports[data.filters.report]&&<>
    <div className="report-caption"><div><strong>{data.title}</strong><p>{displayDate(data.filters.start)} a {displayDate(data.filters.end)} · {data.basis}</p></div><span>Atualizado em {cell(data.generated_at,{key:'',label:'',kind:'datetime'},data.timezone)}</span></div>
    <div className="report-metrics">{data.summary.map(m=><article className="erp-card" key={m.key}><span>{m.label}</span><strong>{m.kind==='money'?currency(m.value):new Intl.NumberFormat('pt-BR',{maximumFractionDigits:0}).format(BigInt(m.value))}</strong><small>Todos os resultados dos filtros aplicados</small></article>)}</div>
    <div className="erp-card report-results"><h2>Detalhamento <small>({data.count} registro(s))</small></h2><p className="report-description">{data.description}</p>{data.results.length?<div className="report-table" tabIndex={0} role="region" aria-label="Tabela do relatório com rolagem"><table><thead><tr>{data.columns.map(c=><th key={c.key} scope="col" className={c.kind==='money'?'is-money':''}>{c.label}</th>)}</tr></thead><tbody>{data.results.map((row,index)=><tr key={row.id||index}>{data.columns.map(c=><td key={c.key} className={c.kind==='money'?'is-money':''}>{cell(row[c.key],c,data.timezone)}</td>)}</tr>)}</tbody></table></div>:<p className="report-empty">Nenhum registro corresponde aos filtros aplicados.</p>}<div className="report-pagination"><button type="button" disabled={loading||exporting||changed||!data.previous} onClick={()=>setPage(v=>v-1)}>Página anterior</button><span>Página {page} · {data.count} registro(s)</span><button type="button" disabled={loading||exporting||changed||!data.next} onClick={()=>setPage(v=>v+1)}>Próxima página</button></div><p className="report-note">O CSV inclui todas as páginas dos filtros aplicados, até {new Intl.NumberFormat('pt-BR').format(options.max_export_rows)} registros por arquivo. Se exceder esse limite, refine os filtros.</p></div>
    </>}
    </>}
  </section>
}
