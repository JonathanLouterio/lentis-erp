import { useFinanceAccess } from '../hooks/useFinanceAccess'
import { useEffect, useState } from 'react'
import { ApiError, getPaymentOptions, getReceivables, receiveInstallment } from '../api'
import type { AccessibleStore, PaymentOptions, Receivable, ReceivablesPage } from '../api'
import { brl, decimal, decimalText, signedDecimal, displayDate, failure, money, dateTime } from './saleMoney'
import FormDialog from './FormDialog'
import './FinanceWindows.css'
import './Sales.css'
import './Receivables.css'

type Props = { store: AccessibleStore; userId: number; onSavingChange: (value: boolean) => void; onDirtyChange: (value: boolean) => void }
type Receipt = { request_id: string; account_id: number; method_id: number; amount: string; card_fee?: string }
type PendingReceipt = { receivableId: number; payload: Receipt }
const states = { pending: 'Pendente', partial: 'Parcial', paid: 'Recebida', cancelled: 'Cancelada' }
const debtorName = (row: Receivable) => row.debtor === 'operator' ? 'Operadora de cartão' : row.customer_name || 'Venda balcão'
const formatMoney = (value: string) => money.format(Number(value))

function ReceiptStatus({status}: {status: Receivable['status']}) {
  const tone = status === 'cancelled' ? 'cancelled' : status === 'paid' ? 'completed' : 'draft'
  return <span className={`erp-sale-badge is-${tone}`}>{states[status]}</span>
}

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
  const [cardFee, setCardFee] = useState('')
  const [accountId, setAccountId] = useState('')
  const [methodId, setMethodId] = useState('')
  const [dirty, setDirty] = useState(false)
  const [pending, setPending] = useState<PendingReceipt | null>(null)
  const rights=useFinanceAccess(store.id,reload)
  const access=rights.access?.receipts
  const immediateMethods = options.methods.filter((method) => ['cash','pix','transfer'].includes(method.kind))
  const isOperator = selected?.debtor === 'operator'
  const value = decimal(amount)
  const fee = isOperator && cardFee.trim() ? decimal(cardFee) : 0n
  const chosenAccount = options.accounts.find(account => String(account.id) === accountId)
  const chosenMethod = immediateMethods.find(method => String(method.id) === methodId)
  const cashClosed = chosenMethod?.kind === 'cash' && chosenAccount?.cash_control_enabled && !chosenAccount.cash_is_open
  const remaining = decimal(selected?.remaining_amount ?? '') ?? 0n
  const settled = value !== null && fee !== null ? value + fee : null
  const feeTargetAllowed = !!chosenAccount && !chosenAccount.cash_box &&
    (chosenMethod?.kind === 'pix' || chosenMethod?.kind === 'transfer')
  const valid = !cashClosed && value !== null && value > 0n && fee !== null && fee >= 0n &&
    !!selected && settled !== null && settled <= remaining && !!chosenAccount && !!chosenMethod &&
    (fee === 0n || (feeTargetAllowed && settled === remaining))


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

  function preferredAccount(kind?: string) {
    return kind === 'cash'
      ? options.accounts.find(account => account.cash_box)
      : options.accounts.find(account => account.code === 'bank') ?? options.accounts.find(account => !account.cash_box)
  }
  function open(row: Receivable) {
    const method = (row.debtor === 'operator' ? immediateMethods.find(item => item.kind === 'transfer') ??
      immediateMethods.find(item => item.kind === 'pix') : undefined) ?? immediateMethods[0]
    setDirty(false); setSuccess(''); setSelected(row); setAmount(row.remaining_amount); setCardFee('')
    setAccountId(String(preferredAccount(method?.kind)?.id || options.accounts[0]?.id || ''))
    setMethodId(String(method?.id || '')); setError('')
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
  function receiptActions(row: Receivable) {
    const reference = `parcela ${row.number} da venda #${row.sale_id}`
    return <>
      {access?.receive && row.can_receive && <button className="erp-table-button" disabled={busy || !!pending} aria-label={`Receber ${reference}`} onClick={() => open(row)}>Receber</button>}
      <button className="erp-table-button" disabled={busy || rights.loading} aria-label={`Histórico da ${reference}`} onClick={() => setHistory(row)}>Histórico</button>
    </>
  }

  if (!access?.view || rights.error) return <section className="erp-card"><p>{rights.error || (rights.loading?'Conferindo permissões de recebimentos…':'Você não tem permissão de consultar parcelas. Solicite a permissão de consulta para selecionar um recebimento.')}</p><button className="erp-secondary-button" disabled={rights.loading} onClick={()=>setReload(v=>v+1)}>Atualizar acessos</button></section>
  return <section className="erp-sales-page erp-receivables-page">
    <div className="erp-page-heading"><span className="erp-kicker">FINANCEIRO</span><h1>Recebimentos</h1><p>Parcelas do cliente e repasses de cartão da unidade {store.name}.</p></div>
    {error && <p className="erp-alert" role="alert">{error}</p>}{success && <p className="erp-sales-success" role="status">{success}</p>}

    {access.balances && options.can_view_balances && <div className="erp-receiving-accounts">{options.accounts.map((account) => <div className="erp-card" key={account.id}><span className="erp-card-label">{account.name}</span><h2>{money.format(Number(account.balance))}</h2><p className="erp-sales-hint">Saldo dos recebimentos registrados no Lentis.</p></div>)}</div>}
    <div className="erp-card"><div className="erp-sales-toolbar"><label>Situação<select aria-label="Situação" value={state} disabled={busy || !!pending} onChange={(event) => {setState(event.target.value);setPage(1)}}><option value="pending">A receber</option><option value="paid">Recebidas</option><option value="cancelled">Canceladas</option><option value="all">Todas</option></select></label><label>Responsável<select aria-label="Responsável" value={debtor} disabled={busy || !!pending} onChange={(event) => {setDebtor(event.target.value);setPage(1)}}><option value="">Todos</option><option value="customer">Cliente</option><option value="operator">Operadora de cartão</option></select></label><span>{data.count} parcelas</span><button className="erp-secondary-button" disabled={busy || loading} onClick={() => setReload((number)=>number+1)}>Atualizar</button></div>
      {loading ? <p role="status">Carregando recebimentos…</p> : !data.results.length ? <p>Nenhuma parcela nesta situação.</p> : <>
        <div className="erp-customer-table-wrap erp-receipts-table">
          <table className="erp-customer-table">
            <thead><tr><th>Venda / parcela</th><th>Responsável</th><th>Vencimento</th><th>Valor</th><th>Recebido líquido</th><th>Saldo</th><th>Situação</th><th>Ação</th></tr></thead>
            <tbody>{data.results.map(row => <tr key={row.id}>
              <td>#{row.sale_id} · {row.number}/{row.installment_count}<small className="erp-sales-item-name">{row.method_name}</small></td>
              <td>{debtorName(row)}</td><td>{displayDate(row.due_date)}</td><td>{formatMoney(row.amount)}</td>
              <td>{formatMoney(row.paid_amount)}{Number(row.card_fee_amount)>0 &&
                <small className="erp-sales-item-name">Taxa: {formatMoney(row.card_fee_amount)}</small>}</td><td>{formatMoney(row.remaining_amount)}</td>
              <td><ReceiptStatus status={row.status} /></td><td>{receiptActions(row)}</td>
            </tr>)}</tbody>
          </table>
        </div>
        <ul className="erp-receipt-cards" aria-label="Parcelas de recebimentos" role="list">
          {data.results.map(row => <li key={row.id}>
            <div className="erp-receipt-card-heading">
              <div><small>Venda #{row.sale_id} · Parcela {row.number}/{row.installment_count}</small><strong>{debtorName(row)}</strong><small>{row.method_name}</small></div>
              <ReceiptStatus status={row.status} />
            </div>
            <dl className="erp-receipt-card-values">
              <div><dt>Saldo a receber</dt><dd>{formatMoney(row.remaining_amount)}</dd></div>
              <div><dt>Vencimento</dt><dd>{displayDate(row.due_date)}</dd></div>
              <div><dt>Valor da parcela</dt><dd>{formatMoney(row.amount)}</dd></div>
              <div><dt>Recebido líquido</dt><dd>{formatMoney(row.paid_amount)}</dd></div>
              {Number(row.card_fee_amount)>0 && <div><dt>Taxa de cartão</dt><dd>{formatMoney(row.card_fee_amount)}</dd></div>}
            </dl>
            <div className="erp-receipt-card-actions">{receiptActions(row)}</div>
          </li>)}
        </ul>
      </>}
      <div className="erp-sales-pagination"><button className="erp-secondary-button" disabled={busy || loading || !data.previous} onClick={()=>setPage((number)=>number-1)}>Anterior</button><span>Página {page}</span><button className="erp-secondary-button" disabled={busy || loading || !data.next} onClick={()=>setPage((number)=>number+1)}>Próxima</button></div>
    </div>
    {!options.can_receive && <p className="erp-sales-hint">Para registrar um recebimento, solicite a permissão específica de receber parcelas.</p>}
    {history && <FormDialog title={`Histórico da parcela ${history.number} · Venda #${history.sale_id}`} sectionLabel="FINANCEIRO · RECEBIMENTOS" subtitle={store.name} onClose={()=>setHistory(null)}><div className="erp-finance-history">{!history.entries.length?<p>Nenhum recebimento registrado.</p>:<ol className="erp-sales-history">{history.entries.map((entry)=><li key={entry.id}><strong>{entry.reversal_of?'Estorno':'Recebimento'} · {money.format(Number(entry.amount))}</strong>{(signedDecimal(entry.card_fee ?? '0') ?? 0n)!==0n && <span>Taxa: {formatMoney(entry.card_fee)} · Valor baixado: {brl((signedDecimal(entry.amount) ?? 0n) + (signedDecimal(entry.card_fee) ?? 0n))}</span>}<span>{entry.account_name} · {entry.method_name} · {dateTime.format(new Date(entry.created_at))} · {entry.creator_username}</span><p>{entry.reason}</p></li>)}</ol>}</div></FormDialog>}
    {(pending || selected && access.receive && options.can_receive) && <FormDialog
      title={pending ? 'Conferir o último recebimento' : `Receber parcela ${selected?.number} · Venda #${selected?.sale_id}`}
      sectionLabel="FINANCEIRO · RECEBIMENTOS" subtitle={store.name} busy={busy || !!pending} dirty={dirty} notice={error}
      onClose={()=>{setSelected(null);setDirty(false);setError('')}}
      actions={!pending && selected && <button className="erp-action-button" type="submit" form="lentis-receipt-form" disabled={busy || rights.loading || !valid}>{busy?'Registrando…':'Confirmar recebimento'}</button>}>
      {error && <p className="erp-alert" role="alert">{error}</p>}
      {pending && <div className="erp-card" role="alert"><p>Repita o mesmo envio para recuperar o resultado e evitar um lançamento duplicado.</p><button className="erp-action-button" disabled={busy || rights.loading || !access.receive} onClick={() => void persist(pending)}>Repetir recebimento com segurança</button></div>}
      {!pending && selected && <form id="lentis-receipt-form" className="erp-finance-form" onSubmit={(event)=>{
        event.preventDefault()
        if(valid && value!==null && fee!==null) void persist({receivableId:selected.id,payload:{
          request_id:crypto.randomUUID(),account_id:Number(accountId),method_id:Number(methodId),
          amount:decimalText(value),card_fee:decimalText(fee),
        }})
      }}>
        <p>Saldo da parcela: {formatMoney(selected.remaining_amount)}</p>
        <label>{isOperator ? 'Valor líquido recebido (R$)' : 'Valor recebido (R$)'}
          <input autoFocus inputMode="decimal" value={amount} disabled={busy || rights.loading} onChange={event=>{setAmount(event.target.value);setDirty(true)}} />
        </label>
        {isOperator && <label>Taxa descontada pela operadora (R$)
          <input inputMode="decimal" placeholder="0,00" value={cardFee} disabled={busy || rights.loading} onChange={event=>{setCardFee(event.target.value);setDirty(true)}} />
        </label>}
        <label>Conta de recebimento<select aria-label="Conta de recebimento" value={accountId} disabled={busy || rights.loading}
          onChange={event=>{setAccountId(event.target.value);setDirty(true)}}>
          <option value="">Selecione</option>{options.accounts.map(account=><option key={account.id} value={account.id}>{account.name}</option>)}
        </select></label>
        <label>Forma de recebimento<select aria-label="Forma de recebimento" value={methodId} disabled={busy || rights.loading} onChange={event=>{
          setDirty(true);setMethodId(event.target.value)
          const preferred=preferredAccount(immediateMethods.find(method=>String(method.id)===event.target.value)?.kind)
          if(preferred)setAccountId(String(preferred.id))
        }}>
          <option value="">Selecione</option>{immediateMethods.map(method=><option key={method.id} value={method.id}>{method.name}</option>)}
        </select></label>
        {cashClosed && <p className="erp-alert" role="alert">Abra o caixa desta conta em Comercial → Caixa antes de confirmar o dinheiro recebido.</p>}
        {isOperator && settled!==null && fee!==null && fee>0n && <>
          <p>Valor a baixar: <strong>{formatMoney(decimalText(settled))}</strong></p>
          {settled!==remaining && <p className="erp-alert" role="status">O valor líquido mais a taxa deve ser igual ao saldo da parcela.</p>}
          {!feeTargetAllowed && <p className="erp-alert" role="status">Selecione uma conta bancária e Pix ou transferência para registrar a taxa.</p>}
        </>}
        <p className="erp-sales-hint">{isOperator ? 'Use os valores do repasse. Somente o valor líquido entra no saldo da conta. Sem taxa, é possível registrar um recebimento parcial.' : 'Confirme somente o valor efetivamente recebido. É possível receber uma parte da parcela.'}</p>
      </form>}

    </FormDialog>}
  </section>
}
