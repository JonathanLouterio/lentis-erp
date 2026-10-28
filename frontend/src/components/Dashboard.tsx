import { useEffect, useState } from 'react'
import { getDashboard } from '../api'
import type { AccessibleStore, DashboardData, DashboardPeriod } from '../api'
import { useInsightAccess } from '../hooks/useInsightAccess'
import { brl, displayDate, failure, signedDecimal } from './saleMoney'
import './Dashboard.css'

export type DashboardAction = 'new-sale'|'new-customer'|'receivables'|'stock'|'cash'|'sale'
type Props={store:AccessibleStore;firstName:string;onAction:(action:DashboardAction,id?:number)=>void}
const amount=(value:string|null)=>value===null?'Acesso restrito':brl(signedDecimal(value)??0n)

function SalesChart({rows,sales,receipts}:{rows:DashboardData['chart'];sales:boolean;receipts:boolean}){
  const [choice,setChoice]=useState<'sales'|'received'>('sales')
  const [active,setActive]=useState<number|null>(null)
  const series=choice==='sales'&&sales?'sales':choice==='received'&&receipts?'received':sales?'sales':'received'
  const values=rows.map(r=>Number(r[series]??0))
  const top=Math.max(0,...values),bottom=Math.min(0,...values),scale=top-bottom||1
  const x=(i:number)=>rows.length===1?400:40+i*720/(rows.length-1)
  const y=(v:number)=>210-(v-bottom)*170/scale
  if(!rows.length||!sales&&!receipts)return null
  return <div className="lentis-chart">
    <div className="lentis-panel-heading"><h2>Evolução no período</h2><label className="lentis-chart-choice">Mostrar<select aria-label="Série do gráfico" value={series} onChange={e=>{setChoice(e.target.value as typeof choice);setActive(null)}}>{sales&&<option value="sales">Vendas</option>}{receipts&&<option value="received">Recebido líquido</option>}</select></label></div>
    <svg viewBox="0 0 800 250" role="img" aria-label={`${series==='sales'?'Vendas':'Recebimentos líquidos'} por dia; consulte a tabela abaixo`} onPointerMove={e=>{const rect=e.currentTarget.getBoundingClientRect();const local=(e.clientX-rect.left)*800/rect.width;setActive(rows.length===1?0:Math.max(0,Math.min(rows.length-1,Math.round((local-40)*(rows.length-1)/720))))}} onPointerLeave={()=>setActive(null)}>
      {[0,0.5,1].map(step=><line key={step} x1="40" x2="760" y1={40+step*170} y2={40+step*170} className="lentis-chart-grid"/>)}
      <line x1="40" x2="760" y1={y(0)} y2={y(0)} className="lentis-chart-zero"/>
      {rows.length===1?<rect x="360" width="80" y={Math.min(y(values[0]),y(0))} height={Math.max(2,Math.abs(y(values[0])-y(0)))} rx="4" className="lentis-chart-bar"/>:<path d={values.map((v,i)=>`${i?'L':'M'}${x(i)},${y(v)}`).join(' ')} className="lentis-chart-line"/>}
      {active!==null&&rows.length>1&&<circle cx={x(active)} cy={y(values[active])} r="5" className="lentis-chart-point"/>}
      <text x="40" y="240">{displayDate(rows[0].date)}</text><text x="760" y="240" textAnchor="end">{displayDate(rows[rows.length-1].date)}</text>
    </svg>
    <p className="lentis-chart-caption" role="status">{active===null?`Maior valor diário: ${amount(rows[values.indexOf(Math.max(...values))][series])}`:`${displayDate(rows[active].date)} · ${amount(rows[active][series])}${sales?` · ${rows[active].sales_count} venda(s)`:""}`}</p>
    <details><summary>Ver dados do gráfico</summary><div className="lentis-table-wrap" tabIndex={0}><table><thead><tr><th>Data</th>{sales&&<th>Vendas</th>}{receipts&&<th>Recebido líquido</th>}</tr></thead><tbody>{rows.map(row=><tr key={row.date}><td>{displayDate(row.date)}</td>{sales&&<td>{amount(row.sales)}</td>}{receipts&&<td>{amount(row.received)}</td>}</tr>)}</tbody></table></div></details>
  </div>
}

export default function Dashboard({store,firstName,onAction}:Props){
  const [period,setPeriod]=useState<DashboardPeriod>({preset:'today'})
  const [picker,setPicker]=useState<DashboardPeriod['preset']>('today')
  const [start,setStart]=useState(''),[end,setEnd]=useState('')
  const [data,setData]=useState<DashboardData|null>(null)
  const [loading,setLoading]=useState(false),[error,setError]=useState(''),[reload,setReload]=useState(0)
  const rights=useInsightAccess(store.id,reload)
  const rightsKey=JSON.stringify([rights.access?.dashboard,rights.access?.sections])
  useEffect(()=>{
    let ignore=false;setData(null);setError('')
    if(!rights.access?.dashboard){setLoading(false);return()=>{ignore=true}}
    setLoading(true)
    void getDashboard(store.id,period).then(next=>{if(!ignore){setData(next);if(period.preset!=='custom'){setStart(next.period.start);setEnd(next.period.end)}}}).catch(e=>{if(!ignore)setError(failure(e))}).finally(()=>{if(!ignore)setLoading(false)})
    return()=>{ignore=true}
  },[store.id,period,reload,rightsKey])
  const sections=rights.access?.sections
  const shortcuts=rights.access?.shortcuts
  const sales=sections?.sales?data?.sales:null
  const receipts=sections?.receipts?data?.receipts:null
  const receivables=sections?.receivables?data?.receivables:null
  const stock=sections?.stock?data?.stock:null
  const cash=sections?.cash?data?.cash:null
  function selectPeriod(value:DashboardPeriod['preset']){setPicker(value);if(value!=='custom')setPeriod({preset:value})}
  return <section className="lentis-dashboard" aria-busy={loading||rights.loading}>
    <header className="lentis-dashboard-heading"><div><span className="erp-kicker">VISÃO GERAL</span><h1>Olá, {firstName}!</h1><p>Acompanhe a operação de <strong>{store.name}</strong>.</p></div>{rights.access?.dashboard&&<div className="lentis-period"><label>Período<select aria-label="Período do dashboard" value={picker} onChange={e=>selectPeriod(e.target.value as DashboardPeriod['preset'])}><option value="today">Hoje</option><option value="7days">Últimos 7 dias</option><option value="month">Mês até hoje</option><option value="custom">Personalizado</option></select></label><button className="erp-secondary-button" disabled={loading} onClick={()=>setReload(v=>v+1)}>Atualizar painel</button></div>}</header>
    {rights.access?.dashboard&&picker==='custom'&&<div className="lentis-custom-period"><label>Início<input aria-label="Início do período" type="date" value={start} onChange={e=>setStart(e.target.value)}/></label><label>Fim<input aria-label="Fim do período" type="date" value={end} onChange={e=>setEnd(e.target.value)}/></label><button className="erp-action-button" disabled={!start||!end||start>end||loading} onClick={()=>setPeriod({preset:'custom',start,end})}>Aplicar período</button><small>Até 366 dias.</small></div>}
    <nav className="lentis-shortcuts" aria-label="Ações rápidas">{shortcuts?.['new-sale']&&<button onClick={()=>onAction('new-sale')}>+ Nova venda</button>}{shortcuts?.['new-customer']&&<button onClick={()=>onAction('new-customer')}>Cadastrar cliente</button>}{shortcuts?.receivables&&<button onClick={()=>onAction('receivables')}>Consultar parcelas</button>}{shortcuts?.stock&&<button onClick={()=>onAction('stock')}>Consultar estoque</button>}</nav>
    {(loading||rights.loading)&&<div className="lentis-loading" role="status">Conferindo indicadores disponíveis…</div>}
    {(error||rights.error)&&<p className="erp-alert" role="alert">{error||rights.error}</p>}
    {!rights.loading&&!rights.access?.dashboard&&<div className="erp-card"><h2>Seu espaço de trabalho</h2><p>Use o menu para acessar os módulos autorizados. A consulta dos indicadores depende da permissão de painel operacional.</p></div>}
    {data&&rights.access?.dashboard&&<>
      <p className="lentis-report-caption">{displayDate(data.period.start)} a {displayDate(data.period.end)} · Atualizado às {new Date(data.generated_at).toLocaleTimeString('pt-BR',{timeZone:data.timezone,hour:'2-digit',minute:'2-digit'})}</p>
      {!Object.values(sections||{}).some(Boolean)&&<div className="erp-card"><p>Os indicadores exigem também as permissões de consulta dos módulos de origem.</p></div>}
      <div className="lentis-kpis">
        {sales&&<><article className="erp-card lentis-kpi is-primary"><span>Vendas no período</span><strong>{amount(sales.total)}</strong><small>{sales.count} finalizada(s) · {sales.variation===null?'Sem base para comparação':`${Number(sales.variation).toLocaleString('pt-BR')}% frente ao período anterior`}</small></article><article className="erp-card lentis-kpi"><span>Ticket médio</span><strong>{amount(sales.ticket)}</strong><small>Valor médio por venda finalizada</small></article></>}
        {receipts&&<article className="erp-card lentis-kpi"><span>Recebido líquido no período</span><strong>{amount(receipts.net)}</strong><small>Recebido {amount(receipts.gross)} · Estornado {amount(receipts.refunds)}</small></article>}
        {receivables&&<article className="erp-card lentis-kpi"><span>A receber do cliente agora</span><strong>{amount(receivables.customer.amount)}</strong><small>{receivables.customer.count} parcela(s) em aberto</small></article>}
      </div>
      <div className="lentis-dashboard-main">{(sales||receipts)&&<section className="erp-card"><SalesChart rows={data.chart} sales={!!sales} receipts={!!receipts}/>{sales&&<p className="lentis-muted">Período anterior: {displayDate(data.period.previous_start)} a {displayDate(data.period.previous_end)} · Vendas {amount(sales.previous_total)}. A comparação usa a mesma quantidade de dias.</p>}</section>}
        {(receivables||stock)&&<section className="erp-card lentis-attention"><h2>Atenção hoje</h2>{receivables&&<><button onClick={()=>onAction('receivables')}><span>Parcelas vencidas do cliente<small>{receivables.overdue.count} parcela(s)</small></span><strong>{amount(receivables.overdue.amount)}</strong></button><button onClick={()=>onAction('receivables')}><span>Vencimentos de hoje<small>{receivables.due_today.count} parcela(s)</small></span><strong>{amount(receivables.due_today.amount)}</strong></button></>}{stock&&<><button disabled={!shortcuts?.stock} onClick={()=>onAction('stock')}><span>Produtos com estoque negativo</span><strong>{stock.negative_count}</strong></button><button disabled={!shortcuts?.stock} onClick={()=>onAction('stock')}><span>No estoque mínimo ou abaixo</span><strong>{stock.low_count}</strong></button></>}<p className="lentis-muted">Alertas e saldos mostram a situação atual, independentemente do período do gráfico.</p></section>}
      </div>
      <div className="lentis-dashboard-secondary">
        {cash&&<section className="erp-card"><div className="lentis-panel-heading"><h2>Caixa físico</h2><button className="erp-table-button" onClick={()=>onAction('cash')}>Ver caixa</button></div><strong className="lentis-section-total">{amount(cash.expected_cash)}</strong><p>{cash.count} caixa(s) aberto(s).</p>{cash.items.map(item=><div className="lentis-mini-row" key={item.id}><span>{item.account_name}<small>Responsável: {item.owner} · #{item.id}</small></span><strong>{amount(item.expected_cash)}</strong></div>)}</section>}
        {stock&&<section className="erp-card"><div className="lentis-panel-heading"><h2>Reposição de estoque</h2>{shortcuts?.stock&&<button className="erp-table-button" onClick={()=>onAction('stock')}>Ver estoque</button>}</div>{stock.items.length?stock.items.map(item=><button disabled={!shortcuts?.stock} className="lentis-product-row" key={item.id} onClick={()=>onAction('stock',item.id)}><span>{item.name}<small>{item.code} · Mínimo {item.minimum}</small></span><strong>{item.quantity}</strong></button>):<p>Nenhum produto no mínimo ou abaixo.</p>}</section>}
      </div>
      {sales&&<section className="erp-card"><div className="lentis-panel-heading"><h2>Últimas vendas do período</h2><button className="erp-table-button" onClick={()=>onAction('sale')}>Ver vendas</button></div>{data.recent_sales.length?<div className="lentis-table-wrap" tabIndex={0}><table><thead><tr><th>Venda</th><th>Cliente</th><th>Finalizada em</th><th>Valor</th><th>Ação</th></tr></thead><tbody>{data.recent_sales.map(item=><tr key={item.id}><td>#{item.id}</td><td>{item.customer_name}</td><td>{new Date(item.completed_at).toLocaleString('pt-BR',{timeZone:data.timezone})}</td><td>{amount(item.total)}</td><td><button className="erp-table-button" onClick={()=>onAction('sale',item.id)}>Abrir venda {item.id}</button></td></tr>)}</tbody></table></div>:<p>Nenhuma venda finalizada neste período.</p>}</section>}
      {receivables&&<section className="erp-card"><div className="lentis-panel-heading"><h2>Recebimentos a acompanhar</h2><button className="erp-table-button" onClick={()=>onAction('receivables')}>Ver financeiro</button></div><p>Da operadora: {amount(receivables.operator.amount)} em {receivables.operator.count} parcela(s). Separado da dívida dos clientes.</p>{receivables.attention.map(item=><div className="lentis-mini-row" key={item.id}><span>{item.customer_name}<small>Venda #{item.sale_id} · {displayDate(item.due_date)} · {item.overdue?'Vencida':'Vence hoje'}</small></span><strong>{amount(item.remaining)}</strong></div>)}</section>}
    </>}
  </section>
}
