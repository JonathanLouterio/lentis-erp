import { useEffect, useState } from 'react'
import { getDashboard } from '../api'
import type { AccessibleStore, DashboardData, DashboardPeriod } from '../api'
import { brl, displayDate, failure, signedDecimal } from './saleMoney'
import './Dashboard.css'

export type DashboardAction = 'new-sale' | 'new-customer' | 'receivables' | 'stock' | 'cash' | 'sale'
type Props = { store: AccessibleStore; firstName: string; onAction: (action: DashboardAction, id?: number) => void }
const amount = (value: string) => brl(signedDecimal(value) ?? 0n)

function SalesChart({ rows }: { rows: DashboardData['chart'] }) {
  const [series, setSeries] = useState<'sales' | 'received'>('sales')
  const [active, setActive] = useState<number | null>(null)
  const values = rows.map(row => Number(row[series]))
  const top = Math.max(0, ...values), bottom = Math.min(0, ...values), scale = top - bottom || 1
  const x = (index: number) => rows.length === 1 ? 400 : 40 + index * 720 / (rows.length - 1)
  const y = (value: number) => 210 - (value - bottom) * 170 / scale
  const path = values.map((value, index) => `${index ? 'L' : 'M'}${x(index)},${y(value)}`).join(' ')
  return <div className="lentis-chart">
    <div className="lentis-panel-heading"><h2>Evolução no período</h2><label className="lentis-chart-choice">Mostrar<select aria-label="Série do gráfico" value={series} onChange={event => { setSeries(event.target.value as 'sales' | 'received'); setActive(null) }}><option value="sales">Vendas</option><option value="received">Recebido líquido</option></select></label></div>
    <svg viewBox="0 0 800 250" role="img" aria-label={`${series === 'sales' ? 'Vendas' : 'Recebimentos líquidos'} por dia; valores disponíveis na tabela abaixo`} onPointerMove={event => {
      const rect = event.currentTarget.getBoundingClientRect(); const local = (event.clientX - rect.left) * 800 / rect.width
      setActive(rows.length === 1 ? 0 : Math.max(0, Math.min(rows.length - 1, Math.round((local - 40) * (rows.length - 1) / 720))))
    }} onPointerLeave={() => setActive(null)}>
      {[0, 0.5, 1].map(step => <line key={step} x1="40" x2="760" y1={40 + step * 170} y2={40 + step * 170} className="lentis-chart-grid" />)}
      <line x1="40" x2="760" y1={y(0)} y2={y(0)} className="lentis-chart-zero" />
      {rows.length === 1 ? <rect x="360" width="80" y={Math.min(y(values[0]), y(0))} height={Math.max(2, Math.abs(y(values[0]) - y(0)))} rx="4" className="lentis-chart-bar" /> : <path d={path} className="lentis-chart-line" />}
      {(rows.length > 1 && active !== null) && <circle cx={x(active ?? 0)} cy={y(values[active ?? 0])} r="5" className="lentis-chart-point" />}
      <text x="40" y="240">{displayDate(rows[0].date)}</text><text x="760" y="240" textAnchor="end">{displayDate(rows[rows.length - 1].date)}</text>
    </svg>
    <p className="lentis-chart-caption" role="status">{active === null ? `Maior valor diário: ${amount(rows[values.indexOf(Math.max(...values))][series])}` : `${displayDate(rows[active].date)} · ${amount(rows[active][series])} · ${rows[active].sales_count} venda(s)`}</p>
    <details><summary>Ver dados do gráfico</summary><div className="lentis-table-wrap" tabIndex={0}><table><thead><tr><th>Data</th><th>Vendas</th><th>Recebido líquido</th></tr></thead><tbody>{rows.map(row => <tr key={row.date}><td>{displayDate(row.date)}</td><td>{amount(row.sales)}</td><td>{amount(row.received)}</td></tr>)}</tbody></table></div></details>
  </div>
}

export default function Dashboard({ store, firstName, onAction }: Props) {
  const [period, setPeriod] = useState<DashboardPeriod>({ preset: 'today' })
  const [picker, setPicker] = useState<DashboardPeriod['preset']>('today')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)
  useEffect(() => {
    let ignore = false; setLoading(true); setError(''); setData(null)
    void getDashboard(store.id, period).then(next => { if (!ignore) { setData(next); if (period.preset !== 'custom') { setStart(next.period.start); setEnd(next.period.end) } } })
      .catch((err: unknown) => { if (!ignore) setError(failure(err)) }).finally(() => { if (!ignore) setLoading(false) })
    return () => { ignore = true }
  }, [store.id, period, reload])
  function selectPeriod(value: DashboardPeriod['preset']) { setPicker(value); if (value !== 'custom') setPeriod({ preset: value }) }
  return <section className="lentis-dashboard" aria-busy={loading}>
    <header className="lentis-dashboard-heading"><div><span className="erp-kicker">VISÃO GERAL</span><h1>Olá, {firstName}!</h1><p>Acompanhe a operação de <strong>{store.name}</strong>.</p></div><div className="lentis-period"><label>Período<select aria-label="Período do dashboard" value={picker} onChange={event => selectPeriod(event.target.value as DashboardPeriod['preset'])}><option value="today">Hoje</option><option value="7days">Últimos 7 dias</option><option value="month">Mês até hoje</option><option value="custom">Personalizado</option></select></label><button className="erp-secondary-button" disabled={loading} onClick={() => setReload(value => value + 1)}>Atualizar painel</button></div></header>
    {picker === 'custom' && <div className="lentis-custom-period"><label>Início<input aria-label="Início do período" type="date" value={start} onChange={event => setStart(event.target.value)} /></label><label>Fim<input aria-label="Fim do período" type="date" value={end} onChange={event => setEnd(event.target.value)} /></label><button className="erp-action-button" disabled={!start || !end || start > end || loading} onClick={() => setPeriod({ preset: 'custom', start, end })}>Aplicar período</button><small>Até 366 dias. Clique em Aplicar para consultar.</small></div>}
    <nav className="lentis-shortcuts" aria-label="Ações rápidas"><button onClick={() => onAction('new-sale')}><span aria-hidden="true">+</span> Nova venda</button><button onClick={() => onAction('new-customer')}>Cadastrar cliente</button><button onClick={() => onAction('receivables')}>Receber parcela</button><button onClick={() => onAction('stock')}>Movimentar estoque</button></nav>
    {loading && <div className="lentis-loading" role="status">Carregando indicadores da unidade…</div>}
    {error && <div className="erp-card"><p className="erp-alert" role="alert">{error}</p><button className="erp-secondary-button" onClick={() => setReload(value => value + 1)}>Tentar novamente</button></div>}
    {data && <>
      <p className="lentis-report-caption">{displayDate(data.period.start)} a {displayDate(data.period.end)} · Atualizado às {new Date(data.generated_at).toLocaleTimeString('pt-BR', { timeZone: data.timezone, hour: '2-digit', minute: '2-digit' })}</p>
      <div className="lentis-kpis">
        <article className="erp-card lentis-kpi is-primary"><span>Vendas no período</span><strong>{amount(data.sales.total)}</strong><small>{data.sales.count} finalizada(s) · {data.sales.variation === null ? 'Sem base para comparação' : `${Number(data.sales.variation) > 0 ? '+' : ''}${Number(data.sales.variation).toLocaleString('pt-BR')}% frente ao período anterior`}</small></article>
        <article className="erp-card lentis-kpi"><span>Ticket médio</span><strong>{amount(data.sales.ticket)}</strong><small>Valor médio por venda finalizada</small></article>
        <article className="erp-card lentis-kpi"><span>Recebido líquido no período</span><strong>{amount(data.receipts.net)}</strong><small>Recebido {amount(data.receipts.gross)} · Estornado {amount(data.receipts.refunds)}</small></article>
        <article className="erp-card lentis-kpi"><span>A receber do cliente agora</span><strong>{amount(data.receivables.customer.amount)}</strong><small>{data.receivables.customer.count} parcela(s) em aberto</small></article>
      </div>
      <div className="lentis-dashboard-main"><section className="erp-card"><SalesChart rows={data.chart} /><p className="lentis-muted">Período anterior: {displayDate(data.period.previous_start)} a {displayDate(data.period.previous_end)} · Vendas {amount(data.sales.previous_total)}. A comparação usa a mesma quantidade de dias.</p></section>
        <section className="erp-card lentis-attention"><div className="lentis-panel-heading"><h2>Atenção hoje</h2><span className="lentis-today">{displayDate(data.today)}</span></div><button className={data.receivables.overdue.count ? 'is-warning' : ''} onClick={() => onAction('receivables')}><span>Parcelas vencidas do cliente<small>{data.receivables.overdue.count} parcela(s)</small></span><strong>{amount(data.receivables.overdue.amount)}</strong></button><button onClick={() => onAction('receivables')}><span>Vencimentos de hoje<small>{data.receivables.due_today.count} parcela(s)</small></span><strong>{amount(data.receivables.due_today.amount)}</strong></button><button className={data.stock.negative_count ? 'is-warning' : ''} onClick={() => onAction('stock')}><span>Produtos com estoque negativo</span><strong>{data.stock.negative_count}</strong></button><button onClick={() => onAction('stock')}><span>No estoque mínimo ou abaixo</span><strong>{data.stock.low_count}</strong></button><p className="lentis-muted">Os alertas e saldos em aberto mostram a situação atual, independentemente do período do gráfico.</p></section>
      </div>
      <div className="lentis-dashboard-secondary">
        <section className="erp-card"><div className="lentis-panel-heading"><h2>Caixa físico</h2><button className="erp-table-button" onClick={() => onAction('cash')}>Ver caixa</button></div><strong className="lentis-section-total">{amount(data.cash.expected_cash)}</strong><p className="lentis-muted">Dinheiro previsto em {data.cash.count} caixa(s) aberto(s).</p>{data.cash.items.length ? data.cash.items.map(cash => <div className="lentis-mini-row" key={cash.id}><span>{cash.account_name}<small>Responsável: {cash.owner} · #{cash.id}</small></span><strong>{amount(cash.expected_cash)}</strong></div>) : <p>Nenhum caixa aberto nesta unidade.</p>}</section>
        <section className="erp-card"><div className="lentis-panel-heading"><h2>Reposição de estoque</h2><button className="erp-table-button" onClick={() => onAction('stock')}>Ver estoque</button></div>{data.stock.items.length ? data.stock.items.map(product => <button className="lentis-product-row" key={product.id} onClick={() => onAction('stock', product.id)}><span>{product.name}<small>{product.code} · Mínimo {Number(product.minimum).toLocaleString('pt-BR')}</small></span><strong className={Number(product.quantity) < 0 ? 'lentis-negative' : ''}>{Number(product.quantity).toLocaleString('pt-BR')}</strong></button>) : <p>Nenhum produto no mínimo ou abaixo.</p>}<p className="lentis-muted">Até 5 produtos, priorizando os menores saldos.</p></section>
      </div>
      <section className="erp-card"><div className="lentis-panel-heading"><h2>Últimas vendas do período</h2><button className="erp-table-button" onClick={() => onAction('sale')}>Ver vendas</button></div>{data.recent_sales.length ? <div className="lentis-table-wrap" tabIndex={0}><table><thead><tr><th>Venda</th><th>Cliente</th><th>Finalizada em</th><th>Valor</th><th>Ação</th></tr></thead><tbody>{data.recent_sales.map(sale => <tr key={sale.id}><td>#{sale.id}</td><td>{sale.customer_name}</td><td>{new Intl.DateTimeFormat('pt-BR', { timeZone: data.timezone, dateStyle: 'short', timeStyle: 'short' }).format(new Date(sale.completed_at))}</td><td>{amount(sale.total)}</td><td><button className="erp-table-button" onClick={() => onAction('sale', sale.id)}>Abrir venda {sale.id}</button></td></tr>)}</tbody></table></div> : <p>Nenhuma venda finalizada neste período.</p>}</section>
      <section className="erp-card"><div className="lentis-panel-heading"><h2>Recebimentos a acompanhar</h2><button className="erp-table-button" onClick={() => onAction('receivables')}>Ver financeiro</button></div><p className="lentis-muted">Da operadora de cartão: {amount(data.receivables.operator.amount)} em {data.receivables.operator.count} parcela(s). Separado da dívida dos clientes.</p>{data.receivables.attention.length ? <div className="lentis-table-wrap" tabIndex={0}><table><thead><tr><th>Cliente</th><th>Venda</th><th>Vencimento</th><th>Saldo</th><th>Situação</th></tr></thead><tbody>{data.receivables.attention.map(item => <tr key={item.id}><td>{item.customer_name || 'Cliente não informado'}</td><td>#{item.sale_id}</td><td>{displayDate(item.due_date)}</td><td>{amount(item.remaining)}</td><td>{item.overdue ? 'Vencida' : 'Vence hoje'}</td></tr>)}</tbody></table></div> : <p>Sem parcelas de clientes vencidas ou com vencimento hoje.</p>}</section>
    </>}
  </section>
}
