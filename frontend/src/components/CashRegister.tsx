import { useEffect, useState } from 'react'
import { ApiError, getCashOptions, getCashPostings, getCashSession, getCashSessions, submitCashOperation } from '../api'
import type { AccessibleStore, CashAttempt, CashPage, CashPosting, CashSession, FinancialAccount } from '../api'
import { brl, dateTime, decimal, decimalText, failure, signedDecimal } from './saleMoney'
import './Sales.css'
import './CashRegister.css'

type Props = { store: AccessibleStore; userId: number; onSavingChange: (busy: boolean) => void; onDirtyChange: (dirty: boolean) => void }
const emptySessions: CashPage<CashSession> = { count: 0, results: [], next: null, previous: null }
const emptyLedger: CashPage<CashPosting> = { count: 0, results: [], next: null, previous: null }
type Form = 'open' | 'supply' | 'withdrawal' | 'close' | null

export default function CashRegister({ store, userId, onSavingChange, onDirtyChange }: Props) {
  const storageKey = `lentis.cash.${userId}.${store.id}`
  const [rows, setRows] = useState(emptySessions)
  const [accounts, setAccounts] = useState<FinancialAccount[]>([])
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('all')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [selected, setSelected] = useState<CashSession | null>(null)
  const [ledger, setLedger] = useState(emptyLedger)
  const [ledgerPage, setLedgerPage] = useState(1)
  const [reload, setReload] = useState(0)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState<CashAttempt | null>(null)
  const [form, setForm] = useState<Form>(null)
  const [accountId, setAccountId] = useState('')
  const [amount, setAmount] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const blocked = busy || !!pending
  const value = decimal(amount)
  const expected = signedDecimal(selected?.expected_cash ?? '0') ?? 0n
  const valid = value !== null && value <= 999999999999n && (form === 'open' ? !!accountId : form === 'close' ? value === expected || !!note.trim() : value > 0n && !!note.trim() && (form !== 'withdrawal' || value <= expected))

  useEffect(() => { onSavingChange(busy); return () => onSavingChange(false) }, [busy, onSavingChange])
  useEffect(() => { onDirtyChange(!!form || !!pending); return () => onDirtyChange(false) }, [form, pending, onDirtyChange])
  useEffect(() => {
    if (!form && !pending) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn)
  }, [form, pending])
  useEffect(() => {
    try { const saved = sessionStorage.getItem(storageKey); if (saved) setPending(JSON.parse(saved) as CashAttempt) } catch { /* Armazenamento opcional. */ }
  }, [storageKey])
  useEffect(() => {
    let ignore = false; setLoading(true)
    void Promise.all([getCashSessions(store.id, page, status), getCashOptions(store.id)])
      .then(([nextRows, options]) => { if (!ignore) { setRows(nextRows); setAccounts(options.accounts) } })
      .catch((err: unknown) => { if (!ignore) setError(failure(err)) }).finally(() => { if (!ignore) setLoading(false) })
    return () => { ignore = true }
  }, [store.id, page, status, reload])
  useEffect(() => {
    if (selectedId === null) return
    let ignore = false; setDetailLoading(true)
    void Promise.all([getCashSession(store.id, selectedId), getCashPostings(store.id, selectedId, ledgerPage)])
      .then(([session, movements]) => { if (!ignore) { setSelected(session); setLedger(movements) } })
      .catch((err: unknown) => { if (!ignore) setError(failure(err)) }).finally(() => { if (!ignore) setDetailLoading(false) })
    return () => { ignore = true }
  }, [store.id, selectedId, ledgerPage, reload])

  function openForm(next: Form) {
    setForm(next); setAmount(next === 'close' ? decimalText(expected) : '0'); setNote(''); setAccountId(String(accounts[0]?.id ?? '')); setError(''); setSuccess('')
  }
  async function persist(attempt: CashAttempt) {
    if (busy) return
    setBusy(true); setError('')
    try { sessionStorage.setItem(storageKey, JSON.stringify(attempt)) } catch { /* Mantemos o envio em memória. */ }
    try {
      const result = await submitCashOperation(store.id, attempt)
      setSelectedId(attempt.action === 'open' ? result.id : attempt.sessionId); setLedgerPage(1); setPage(1); setReload(value => value + 1)
      setForm(null); setPending(null); setSuccess(attempt.action === 'open' ? 'Caixa aberto. Os recebimentos em dinheiro nesta conta serão registrados aqui.' : attempt.action === 'close' ? 'Caixa fechado. A contagem e a diferença ficaram registradas no histórico.' : 'Movimento registrado no caixa.')
      try { sessionStorage.removeItem(storageKey) } catch { /* Armazenamento opcional. */ }
    } catch (err) {
      setError(failure(err))
      if (!(err instanceof ApiError) || err.status === 0 || err.status >= 500) { setPending(attempt); setForm(null) }
      else { setPending(null); setReload(value => value + 1); try { sessionStorage.removeItem(storageKey) } catch { /* Armazenamento opcional. */ } }
    } finally { setBusy(false) }
  }
  function submit() {
    if (blocked || !valid || value === null || !form) return
    const request_id = crypto.randomUUID()
    if (form === 'open') void persist({ action: 'open', payload: { request_id, account_id: Number(accountId), amount: decimalText(value), note: note.trim() } })
    else if (selected) {
      if (form === 'close') void persist({ action: 'close', sessionId: selected.id, payload: { request_id, counted_amount: decimalText(value), note: note.trim() } })
      else void persist({ action: 'move', sessionId: selected.id, payload: { request_id, kind: form, amount: decimalText(value), reason: note.trim() } })
    }
  }

  return <section className="erp-sales-page erp-cash-page">
    <div className="erp-page-heading erp-list-heading"><div><span className="erp-kicker">COMERCIAL</span><h1>Caixa</h1><p>Dinheiro físico da unidade {store.name}. Pix e cartões permanecem no financeiro.</p></div><button className="erp-action-button" disabled={blocked || loading || !!form || !accounts.length} onClick={() => openForm('open')}>Abrir caixa</button></div>
    {error && <p className="erp-alert" role="alert">{error}</p>}{success && <p className="erp-sales-success" role="status">{success}</p>}
    {pending && <div className="erp-card" role="alert"><h2>Conferir o último envio</h2><p>A resposta não foi confirmada. Repita a mesma operação para recuperar o resultado sem duplicar o lançamento.</p><button className="erp-action-button" disabled={busy} onClick={() => void persist(pending)}>Repetir envio com segurança</button></div>}
    {!accounts.length && !loading && <p className="erp-sales-hint">Cadastre uma conta de dinheiro físico no admin ou use a conta inicial “Caixa da loja”.</p>}
    {form && <div className="erp-card erp-cash-form"><h2>{form === 'open' ? 'Abrir caixa' : form === 'close' ? 'Conferir e fechar caixa' : form === 'supply' ? 'Registrar suprimento' : 'Registrar sangria / retirada'}</h2>
      {form === 'open' && <label>Conta de caixa<select aria-label="Conta de caixa" value={accountId} disabled={blocked} onChange={event => setAccountId(event.target.value)}><option value="">Selecione</option>{accounts.map(account => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label>}
      <label>{form === 'open' ? 'Dinheiro inicial (R$)' : form === 'close' ? 'Dinheiro contado (R$)' : 'Valor (R$)'}<input aria-label="Valor do caixa" inputMode="decimal" value={amount} disabled={blocked} onChange={event => setAmount(event.target.value)} /></label>
      {form === 'close' && <p>Previsto: <strong>{brl(expected)}</strong> · Diferença: <strong>{value === null ? 'Revisar contagem' : brl(value - expected)}</strong></p>}
      <label>{form === 'open' ? 'Observação (opcional)' : form === 'close' ? 'Justificativa da diferença / observação' : 'Motivo'}<textarea aria-label="Motivo do caixa" maxLength={255} value={note} disabled={blocked} onChange={event => setNote(event.target.value)} /></label>
      <p className="erp-sales-hint">{form === 'open' ? 'Informe o dinheiro efetivamente disponível. Abrir o caixa não registra uma venda ou um recebimento de cliente.' : form === 'close' ? 'O fechamento preserva o histórico. Diferenças exigem justificativa; o dinheiro contado não vira um recebimento.' : 'Suprimento adiciona dinheiro e retirada remove dinheiro físico. Estes movimentos não baixam parcelas de clientes.'}</p>
      <div className="erp-sales-actions"><button className="erp-secondary-button" disabled={blocked} onClick={() => setForm(null)}>Voltar</button><button className="erp-action-button" disabled={blocked || detailLoading || !valid} onClick={submit}>{busy ? 'Registrando…' : form === 'open' ? 'Confirmar abertura' : form === 'close' ? 'Confirmar fechamento' : 'Confirmar movimento'}</button></div>
    </div>}
    <div className="erp-card"><div className="erp-sales-toolbar"><label>Situação<select aria-label="Situação do caixa" value={status} disabled={blocked || !!form} onChange={event => { setStatus(event.target.value); setPage(1) }}><option value="all">Todos</option><option value="open">Abertos</option><option value="closed">Fechados</option></select></label><button className="erp-secondary-button" disabled={blocked || loading || detailLoading} onClick={() => setReload(value => value + 1)}>Atualizar caixa</button></div>
      {loading ? <p role="status">Carregando caixas…</p> : !rows.results.length ? <p>Nenhuma abertura registrada.</p> : <div className="erp-customer-table-wrap"><table className="erp-customer-table"><thead><tr><th>Caixa</th><th>Responsável</th><th>Abertura</th><th>Situação</th><th>Previsto</th><th>Ação</th></tr></thead><tbody>{rows.results.map(session => <tr key={session.id}><td>#{session.id} · {session.account_name}</td><td>{session.owner_username}</td><td>{dateTime.format(new Date(session.opened_at))}</td><td>{session.closed_at ? 'Fechado' : 'Aberto'}</td><td>{brl(signedDecimal(session.expected_cash) ?? 0n)}</td><td><button className="erp-table-button" disabled={blocked || !!form} onClick={() => { setSelectedId(session.id); setSelected(null); setLedgerPage(1) }}>Consultar caixa {session.id}</button></td></tr>)}</tbody></table></div>}
      <div className="erp-sales-pagination"><button className="erp-secondary-button" disabled={blocked || !!form || !rows.previous} onClick={() => setPage(value => value - 1)}>Anterior</button><span>Página {page} · {rows.count} aberturas</span><button className="erp-secondary-button" disabled={blocked || !!form || !rows.next} onClick={() => setPage(value => value + 1)}>Próxima</button></div>
    </div>
    {detailLoading ? <p role="status">Conferindo movimentos…</p> : selected && <div className="erp-card"><div className="erp-cash-detail-heading"><div><h2>Caixa #{selected.id} · {selected.closed_at ? 'Fechado' : 'Aberto'}</h2><p>{selected.account_name} · Responsável: {selected.owner_username}</p></div><strong className="erp-cash-total">{brl(expected)}</strong></div>
      <dl className="erp-cash-summary"><div><dt>Dinheiro inicial</dt><dd>{brl(decimal(selected.opening_amount) ?? 0n)}</dd></div><div><dt>Dinheiro previsto</dt><dd>{brl(expected)}</dd></div>{selected.closed_at && <><div><dt>Dinheiro contado</dt><dd>{brl(decimal(selected.counted_amount ?? '0') ?? 0n)}</dd></div><div><dt>Diferença registrada</dt><dd>{brl(signedDecimal(selected.difference ?? '0') ?? 0n)}</dd></div></>}</dl>
      {selected.opening_note && <p>Abertura: {selected.opening_note}</p>}{selected.closed_at && <p>Fechado em {dateTime.format(new Date(selected.closed_at))} por {selected.closer_username}. {selected.closing_note}</p>}
      {selected.can_operate && <div className="erp-sales-actions"><button className="erp-secondary-button" disabled={blocked || !!form} onClick={() => openForm('supply')}>Suprimento</button><button className="erp-secondary-button" disabled={blocked || !!form} onClick={() => openForm('withdrawal')}>Sangria / retirada</button><button className="erp-action-button" disabled={blocked || !!form} onClick={() => openForm('close')}>Fechar caixa</button></div>}
      {!selected.closed_at && !selected.can_operate && <p className="erp-sales-hint">Movimentos manuais e fechamento dependem do responsável ou de permissão para operar outros caixas.</p>}
      <h3>Movimentos</h3>{!ledger.results.length ? <p>Nenhum movimento registrado.</p> : <div className="erp-customer-table-wrap"><table className="erp-customer-table"><thead><tr><th>Data</th><th>Tipo</th><th>Valor</th><th>Operador</th><th>Motivo</th></tr></thead><tbody>{ledger.results.map(posting => <tr key={posting.id}><td>{dateTime.format(new Date(posting.created_at))}</td><td>{posting.kind_label}{posting.sale_id && <small className="erp-sales-item-name">Venda #{posting.sale_id}</small>}</td><td>{brl(signedDecimal(posting.amount) ?? 0n)}</td><td>{posting.creator_username}</td><td>{posting.reason}</td></tr>)}</tbody></table></div>}
      <div className="erp-sales-pagination"><button className="erp-secondary-button" disabled={blocked || !!form || !ledger.previous} onClick={() => setLedgerPage(value => value - 1)}>Movimentos anteriores</button><span>Página {ledgerPage} · {ledger.count} movimentos</span><button className="erp-secondary-button" disabled={blocked || !!form || !ledger.next} onClick={() => setLedgerPage(value => value + 1)}>Próximos movimentos</button></div>
    </div>}
  </section>
}
