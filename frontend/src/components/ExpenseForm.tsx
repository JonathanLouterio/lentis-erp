import { useState } from 'react'
import type { ExpenseInput, PayableOptions } from '../api'
import { decimal, decimalText, displayDate, paymentSchedule, today } from './saleMoney'

type Props = {
  categories: PayableOptions['expense_categories']
  disabled: boolean
  onChange: () => void
  onSubmit: (values: ExpenseInput) => void
}

export default function ExpenseForm({categories, disabled, onChange, onSubmit}: Props) {
  const [category, setCategory] = useState('')
  const [description, setDescription] = useState('')
  const [payee, setPayee] = useState('')
  const [reference, setReference] = useState('')
  const [amount, setAmount] = useState('')
  const [firstDue, setFirstDue] = useState(today())
  const [count, setCount] = useState('1')
  const total = decimal(amount)
  const preview = total === null ? [] : paymentSchedule(total, Number(count), firstDue, 'months', 1)
  const valid = categories.some(option => option.value === category) && !!description.trim() && preview.length > 0
  return <form className="erp-finance-form" onChange={onChange} onSubmit={event => {
    event.preventDefault()
    if (!disabled && valid && total !== null) onSubmit({
      category, description: description.trim(), payee: payee.trim(), reference: reference.trim(), total: decimalText(total),
      installment_count: Number(count), first_due_date: firstDue, interval_unit: 'months', interval_count: 1,
    })
  }}>
    <p>Lance uma despesa da unidade. Depois de pagar, abra o título para registrar a saída na conta ou no caixa.</p>
    <fieldset disabled={disabled}>
      <legend>Dados da despesa</legend>
      <label>Categoria<select required value={category} onChange={event => setCategory(event.target.value)}>
        <option value="">Selecione a categoria</option>
        {categories.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select></label>
      <label>Descrição<input required maxLength={160} placeholder="Ex.: Aluguel da loja — novembro" value={description} onChange={event => setDescription(event.target.value)} /></label>
      <div className="payable-fields">
        <label>Favorecido (opcional)<input maxLength={140} value={payee} onChange={event => setPayee(event.target.value)} /></label>
        <label>Referência do documento (opcional)<input maxLength={120} value={reference} onChange={event => setReference(event.target.value)} /></label>
        <label>Valor total (R$)<input required inputMode="decimal" placeholder="0,00" value={amount} onChange={event => setAmount(event.target.value)} /></label>
        <label>{count === '1' ? 'Vencimento' : 'Primeiro vencimento'}<input required type="date" value={firstDue} onChange={event => setFirstDue(event.target.value)} /></label>
        <label>Parcelas mensais<input required type="number" min={1} max={12} value={count} onChange={event => setCount(event.target.value)} /></label>
      </div>
      {preview.length > 0 && <ol className="payable-preview" aria-label="Prévia das parcelas">
        {preview.map((row, index) => <li key={row.date}><span>Parcela {index + 1} · {displayDate(row.date)}</span><strong>R$ {decimalText(row.amount).replace('.', ',')}</strong></li>)}
      </ol>}
      <button type="submit" className="erp-action-button" disabled={disabled || !valid}>Salvar despesa</button>
    </fieldset>
  </form>
}
