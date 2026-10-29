import { useFinanceAccess } from '../hooks/useFinanceAccess'
import { useEffect, useState } from 'react'
import { ApiError, getPaymentOptions, getReceivables, receiveInstallment } from '../api'
import type { AccessibleStore, PaymentOptions, Receivable, ReceivablesPage } from '../api'
import { decimal, decimalText, displayDate, failure, money, dateTime } from './saleMoney'
import FormDialog from './FormDialog'
import './FinanceWindows.css'
import './Sales.css'

type Props = { store: AccessibleStore; userId: number; onSavingChange: (value: boolean) => void; onDirtyChange: (value: boolean) => void }
type Receipt = { request_id: string; account_id: number; method_id: number; amount: string }
type PendingReceipt = { receivableId: number; payload: Receipt }
const states = { pending: 'Pendente', partial: 'Parcial', paid: 'Recebida', cancelled: 'Cancelada' }

export default function Receivables({ store, userId, onSavingChange, onDirtyChange }: Props) {
  const storageKey = `lentis.receipt.${userId}.${store.id}`
  const [data, setData] = useState<ReceivablesPage>({ count: 0, results: [], next: null, previous: null })
  const [options, setOptions] = useState<PaymentOptions>({ methods: [], accounts: [], can_receive: false, allow_negative_stock: false, discount_limit_percentage: "100.00", discount_policy_configured: false, can_approve_discount: false, discount_role: "" })
  const [state, setState] = useState('pending')
  const [debtor, setDebtor] = useState('')
  const [page, setPage] = useState(1)
  const [reload, setReload] = useState(0)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [selected, setSelected] = useState<Receivable | null>(null)
  const [history, setHistory] = useState<Receivable | null>(null)
  const [amount, setAmount] = useState('')
  const [accountId, setAccountId] = useState('')
  const [methodId, setMethodId] = useState('')
  const [dirty, setDirty] = useState(false)
  const [pending, setPending] = useState<PendingReceipt | null>(null)
  const rights=useFinanceAccess(store.id,reload)
  const access=rights.access?.receipts
  const immediateMethods = options.methods.filter((method) => ['cash','pix','transfer'].includes(method.kind))
  const value = decimal(amount)
  const chosenAccount = options.accounts.find(account => String(account.id) === accountId)
  const cashClosed = immediateMethods.find(method => String(method.id) === methodId)?.kind === 'cash' && chosenAccount?.cash_control_enabled && !chosenAccount.cash_is_open
  const valid = !cashClosed && value !== null && value > 0n && !!selected && value <= (decimal(selected.remaining_amount) ?? 0n) && !!accountId && !!methodId

  useEffect(() => { onSavingChange(busy); return () => onSavingChange(false) }, [busy, onSavingChange])
  useEffect(() => { onDirtyChange(dirty || !!pending); return () => onDirtyChange(false) }, [dirty, pending, onDirtyChange])
  useEffect(() => {
    if (!selected && !pending) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = "" }
    window.addEventListener("beforeunload", warn)
    return () => window.removeEventListener("beforeunload", warn)
  }, [selected, pending])
  useEffect(() => {
    try { const saved = sessionStorage.getItem(storageKey); if (saved) setPending(JSON.parse(saved) as PendingReceipt) } catch { /* Sem armazenamento disponível. */ }
  }, [storageKey])
  useEffect(() => {
    let ignore = false
    if (!access?.view) {setData({count:0,results:[],next:null,previous:null});setSelected(null);setHistory(null);setLoading(false);return}
    setLoading(true)
    void Promise.all([getReceivables(store.id,page,state,debtor), getPaymentOptions(store.id)])
      .then(([rows,nextOptions]) => { if (!ignore) { setData(rows); setOptions(nextOptions) } })
      .catch((err: unknown) => { if (!ignore) setError(failure(err)) }).finally(() => { if (!ignore) setLoading(false) })
    return () => { ignore = true }
  }, [store.id,page,state,debtor,reload,access?.view,access?.receive,access?.balances])

  function open(row: Receivable) {
    setDirty(false); setSuccess(''); setSelected(row); setAmount(row.remaining_amount); setAccountId(String((immediateMethods[0]?.kind === 'cash' ? options.accounts.find(account => account.cash_box || account.code === 'cash') : options.accounts.find(account => account.code === 'bank'))?.id || options.accounts[0]?.id || '')); setMethodId(String(immediateMethods[0]?.id || '')); setError('')
  }
  async function persist(attempt: PendingReceipt) {
    if (busy || rights.loading || !access?.receive) return
    setBusy(true); setError('')
    try { sessionStorage.setItem(storageKey,JSON.stringify(attempt)) } catch { /* O envio também fica em memória. */ }
    try {
      await receiveInstallment(store.id,attempt.receivableId,attempt.payload)
      setDirty(false); setSelected(null); setPending(null); setHistory(null); setReload((number) => number+1); setSuccess('Recebimento registrado. O saldo da parcela e da conta foram atualizados.')
      try { sessionStorage.removeItem(storageKey) } catch { /* Sem armazenamento disponível. */ }
    } catch (err) {
      setError(failure(err))
      if (!(err instanceof ApiError) || err.status === 0 || err.status >= 500) { setPending(attempt); setSelected(null) }
      else { setPending(null); setReload(v=>v+1); try { sessionStorage.removeItem(storageKey) } catch { /* Sem armazenamento disponível. */ } }
    } finally { setBusy(false) }
  }
  if (!access?.view || rights.error) return <section className="erp-card"><p>{rights.error || (rights.loading?'Conferindo permissões de recebimentos…':'Você não tem permissão de consultar parcelas. Solicite a permissão de consulta para selecionar um recebimento.')}</p><button className="erp-secondary-button" disabled={rights.loading} onClick={()=>setReload(v=>v+1)}>Atualizar acessos</button></section>
  return <section className="erp-sales-page erp-receivables-page">
    <div className="erp-page-heading"><span className="erp-kicker">FINANCEIRO</span><h1>Recebimentos</h1><p>Parcelas do cliente e repasses de cartão da unidade {store.name}.</p></div>
    {error && <p className="erp-alert" role="alert">{error}</p>}{success && <p className="erp-sales-success" role="status">{success}</p>}

    {access.balances && options.can_view_balances && <div className="erp-receiving-accounts">{options.accounts.map((account) => <div className="erp-card" key={account.id}><span className="erp-card-label">{account.name}</span><h2>{money.format(Number(account.balance))}</h2><p className="erp-sales-hint">Saldo dos recebimentos registrados no Lentis.</p></div>)}</div>}
    <div className="erp-card"><div className="erp-sales-toolbar"><label>Situação<select aria-label="Situação" value={state} disabled={busy || !!pending} onChange={(event) => {setState(event.target.value);setPage(1)}}><option value="pending">A receber</option><option value="paid">Recebidas</option><option value="cancelled">Canceladas</option><option value="all">Todas</option></select></label><label>Responsável<select aria-label="Responsável" value={debtor} disabled={busy || !!pending} onChange={(event) => {setDebtor(event.target.value);setPage(1)}}><option value="">Todos</option><option value="customer">Cliente</option><option value="operator">Operadora de cartão</option></select></label><span>{data.count} parcelas</span><button className="erp-secondary-button" disabled={busy || loading} onClick={() => setReload((number)=>number+1)}>Atualizar</button></div>
      {loading ? <p role="status">Carregando recebimentos…</p> : !data.results.length ? <p>Nenhuma parcela nesta situação.</p> : <div className="erp-customer-table-wrap"><table className="erp-customer-table"><thead><tr><th>Venda / parcela</th><th>Responsável</th><th>Vencimento</th><th>Valor</th><th>Recebido</th><th>Saldo</th><th>Situação</th><th>Ação</th></tr></thead><tbody>{data.results.map((row)=><tr key={row.id}><td>#{row.sale_id} · {row.number}/{row.installment_count}<small className="erp-sales-item-name">{row.method_name}</small></td><td>{row.debtor==='operator'?'Operadora de cartão':row.customer_name||'Venda balcão'}</td><td>{displayDate(row.due_date)}</td><td>{money.format(Number(row.amount))}</td><td>{money.format(Number(row.paid_amount))}</td><td>{money.format(Number(row.remaining_amount))}</td><td><span className={`erp-sale-badge is-${row.status==='cancelled'?'cancelled':row.status==='paid'?'completed':'draft'}`}>{states[row.status]}</span></td><td>{access.receive && row.can_receive && <button className="erp-table-button" disabled={busy || !!pending} aria-label={`Receber parcela ${row.id}`} onClick={()=>open(row)}>Receber</button>}<button className="erp-table-button" disabled={busy || rights.loading} onClick={()=>setHistory(row)}>Histórico</button></td></tr>)}</tbody></table></div>}
      <div className="erp-sales-pagination"><button className="erp-secondary-button" disabled={busy || loading || !data.previous} onClick={()=>setPage((number)=>number-1)}>Anterior</button><span>Página {page}</span><button className="erp-secondary-button" disabled={busy || loading || !data.next} onClick={()=>setPage((number)=>number+1)}>Próxima</button></div>
    </div>
    {!options.can_receive && <p className="erp-sales-hint">Para registrar um recebimento, solicite a permissão específica de receber parcelas.</p>}
    {history && <FormDialog title={`Histórico da parcela ${history.number} · Venda #${history.sale_id}`} sectionLabel="FINANCEIRO · RECEBIMENTOS" subtitle={store.name} onClose={()=>setHistory(null)}><div className="erp-finance-history">{!history.entries.length?<p>Nenhum recebimento registrado.</p>:<ol className="erp-sales-history">{history.entries.map((entry)=><li key={entry.id}><strong>{entry.reversal_of?'Estorno':'Recebimento'} · {money.format(Number(entry.amount))}</strong><span>{entry.account_name} · {entry.method_name} · {dateTime.format(new Date(entry.created_at))} · {entry.creator_username}</span><p>{entry.reason}</p></li>)}</ol>}</div></FormDialog>}
    {(pending || selected && access.receive && options.can_receive) && <FormDialog
      title={pending ? 'Conferir o último recebimento' : `Receber parcela ${selected?.number} · Venda #${selected?.sale_id}`}
      sectionLabel="FINANCEIRO · RECEBIMENTOS" subtitle={store.name} busy={busy || !!pending} dirty={dirty} notice={error}
      onClose={()=>{setSelected(null);setDirty(false);setError('')}}
      actions={!pending && selected && <button className="erp-action-button" type="submit" form="lentis-receipt-form" disabled={busy || rights.loading || !valid}>{busy?'Registrando…':'Confirmar recebimento'}</button>}>
      {error && <p className="erp-alert" role="alert">{error}</p>}
      {pending && <div className="erp-card" role="alert"><p>Repita o mesmo envio para recuperar o resultado e evitar um lançamento duplicado.</p><button className="erp-action-button" disabled={busy || rights.loading || !access.receive} onClick={() => void persist(pending)}>Repetir recebimento com segurança</button></div>}
      {!pending && selected && <form id="lentis-receipt-form" className="erp-finance-form" onSubmit={(event)=>{event.preventDefault();if(valid && value!==null)void persist({receivableId:selected.id,payload:{request_id:crypto.randomUUID(),account_id:Number(accountId),method_id:Number(methodId),amount:decimalText(value)}})}}><p>Saldo: {money.format(Number(selected.remaining_amount))}</p><label>Valor recebido (R$)<input aria-label="Valor recebido (R$)" autoFocus inputMode="decimal" value={amount} disabled={busy || rights.loading} onChange={(event)=>{setAmount(event.target.value);setDirty(true)}} /></label><label>Conta de recebimento<select aria-label="Conta de recebimento" value={accountId} disabled={busy || rights.loading} onChange={(event)=>{setAccountId(event.target.value);setDirty(true)}}><option value="">Selecione</option>{options.accounts.map((account)=><option key={account.id} value={account.id}>{account.name}</option>)}</select></label><label>Forma de recebimento<select aria-label="Forma de recebimento" value={methodId} disabled={busy || rights.loading} onChange={(event)=>{setDirty(true);setMethodId(event.target.value);const method=immediateMethods.find(method=>String(method.id)===event.target.value);const preferred=method?.kind==='cash'?options.accounts.find(account=>account.cash_box||account.code==='cash'):options.accounts.find(account=>account.code==='bank');if(preferred)setAccountId(String(preferred.id))}}><option value="">Selecione</option>{immediateMethods.map((method)=><option key={method.id} value={method.id}>{method.name}</option>)}</select></label><>{cashClosed && <p className="erp-alert" role="alert">Abra o caixa desta conta em Comercial → Caixa antes de confirmar o dinheiro recebido.</p>}</><p className="erp-sales-hint">Confirme somente o valor efetivamente recebido. É possível receber uma parte da parcela.</p></form>}
    </FormDialog>}
  </section>
}
