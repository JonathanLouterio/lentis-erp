import { useState } from 'react'
import type { PaymentOptions } from '../api'
import { brl, decimal, decimalText, paymentSchedule, today } from './saleMoney'

export type PaymentPlanRow = {
  key: string; methodId: string; accountId: string; amount: string; auto: boolean
  count: number; due: string; confirmed: boolean; intervalUnit: 'months' | 'days'; intervalCount: number
}
type Props = { options: PaymentOptions; total: bigint; blocked: boolean; onApply: (payments: PaymentPlanRow[]) => void }

export default function PaymentPlanBuilder({ options, total, blocked, onApply }: Props) {
  const immediate = options.methods.filter(method => ['cash', 'pix', 'transfer'].includes(method.kind))
  const deferred = options.methods.filter(method => ['credit', 'store_credit', 'boleto'].includes(method.kind))
  const [entry, setEntry] = useState('0')
  const [entryMethod, setEntryMethod] = useState(String(immediate.find(method => method.kind === 'pix')?.id ?? immediate[0]?.id ?? ''))
  const [entryAccount, setEntryAccount] = useState(String(options.accounts.find(account => account.code === 'bank')?.id ?? options.accounts[0]?.id ?? ''))
  const [confirmed, setConfirmed] = useState(false)
  const [methodId, setMethodId] = useState(String(deferred.find(method => method.kind === 'store_credit')?.id ?? deferred[0]?.id ?? ''))
  const [accountId, setAccountId] = useState(entryAccount)
  const [count, setCount] = useState(1)
  const [due, setDue] = useState(today())
  const [unit, setUnit] = useState<'months' | 'days'>('months')
  const [interval, setInterval] = useState(1)
  const amount = decimal(entry)
  const remaining = total - (amount ?? 0n)
  const method = deferred.find(candidate => String(candidate.id) === methodId)
  const maximum = method?.installment_limit ?? 12
  const schedule = paymentSchedule(remaining, count, due, unit, interval)
  const valid = amount !== null && amount >= 0n && remaining > 0n && count <= maximum && schedule.length === count && !!method && options.accounts.some(account => String(account.id) === accountId) && (amount === 0n || (immediate.some(method => String(method.id) === entryMethod) && options.accounts.some(account => String(account.id) === entryAccount)))

  function apply() {
    if (!valid || blocked || amount === null) return
    const rows: PaymentPlanRow[] = []
    if (amount > 0n) rows.push({ key: crypto.randomUUID(), methodId: entryMethod, accountId: entryAccount, amount: decimalText(amount), auto: false, count: 1, due: today(), confirmed, intervalUnit: 'months', intervalCount: 1 })
    rows.push({ key: crypto.randomUUID(), methodId, accountId, amount: decimalText(remaining), auto: true, count, due, confirmed: false, intervalUnit: unit, intervalCount: interval })
    onApply(rows)
  }

  return <div className="erp-payment-builder">
    <h3>Montar entrada e saldo parcelado</h3>
    <p className="erp-sales-hint">A entrada pode ser zero. Aplique o plano para substituir os pagamentos atuais ou feche a montagem para mantê-los.</p>
    <div className="erp-payment-builder-fields">
      <label>Entrada (R$)<input aria-label="Valor da entrada" inputMode="decimal" value={entry} disabled={blocked} onChange={event => setEntry(event.target.value)} /></label>
      <label>Forma da entrada<select aria-label="Forma da entrada" value={entryMethod} disabled={blocked || amount === 0n} onChange={event => setEntryMethod(event.target.value)}><option value="">Selecione</option>{immediate.map(method => <option key={method.id} value={method.id}>{method.name}</option>)}</select></label>
      <label>Conta da entrada<select aria-label="Conta da entrada" value={entryAccount} disabled={blocked || amount === 0n} onChange={event => setEntryAccount(event.target.value)}><option value="">Selecione</option>{options.accounts.map(account => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label>
    </div>
    <label className="erp-checkout-checkbox"><input aria-label="Entrada recebida" type="checkbox" checked={confirmed} disabled={blocked || amount === 0n} onChange={event => setConfirmed(event.target.checked)} />Entrada já recebida e conferida</label>
    <div className="erp-payment-builder-fields">
      <label>Forma do saldo<select aria-label="Forma do saldo" value={methodId} disabled={blocked} onChange={event => { setMethodId(event.target.value); setCount(1) }}><option value="">Selecione</option>{deferred.map(method => <option key={method.id} value={method.id}>{method.name}</option>)}</select></label>
      <label>Conta do saldo<select aria-label="Conta do saldo" value={accountId} disabled={blocked} onChange={event => setAccountId(event.target.value)}><option value="">Selecione</option>{options.accounts.map(account => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label>
      <label>Parcelas do saldo<select aria-label="Parcelas do saldo" value={count} disabled={blocked} onChange={event => setCount(Number(event.target.value))}>{Array.from({ length: maximum }, (_, index) => <option key={index} value={index + 1}>{index + 1}x sem juros</option>)}</select></label>
      <label>Primeiro vencimento<input aria-label="Primeiro vencimento do saldo" type="date" value={due} disabled={blocked} onChange={event => setDue(event.target.value)} /></label>
      <label>Intervalo<select aria-label="Unidade do intervalo do saldo" value={unit} disabled={blocked || count === 1} onChange={event => { setUnit(event.target.value as 'months' | 'days'); setInterval(event.target.value === 'days' ? 30 : 1) }}><option value="months">Meses</option><option value="days">Dias</option></select></label>
      <label>{unit === 'months' ? 'A cada quantos meses' : 'A cada quantos dias'}<input aria-label="Intervalo do saldo" type="number" min={1} max={unit === 'months' ? 12 : 365} value={interval} disabled={blocked || count === 1} onChange={event => setInterval(Number(event.target.value))} /></label>
    </div>
    <p><strong>Saldo a parcelar: {brl(remaining)}</strong></p>
    {!valid && <p className="erp-sales-hint">Informe entrada menor que o total, forma, conta e vencimentos válidos. Respeite o limite de {maximum} parcela(s) e o mínimo de um centavo por parcela.</p>}
    <button className="erp-action-button" disabled={blocked || !valid} onClick={apply}>Aplicar entrada e parcelas</button>
  </div>
}
