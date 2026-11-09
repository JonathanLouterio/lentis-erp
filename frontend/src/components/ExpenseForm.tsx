import { useState } from 'react'
import type { ExpenseInput, PayableOptions } from '../api'
import { decimal, decimalText, displayDate, paymentSchedule, today } from './saleMoney'

type Props = {
  options: PayableOptions
  canPay: boolean
  disabled: boolean
  onChange: () => void
  onSubmit: (values: ExpenseInput) => void
}

export default function ExpenseForm({options, canPay, disabled, onChange, onSubmit}: Props) {
  const [category, setCategory] = useState('')
  const [description, setDescription] = useState('')
  const [payee, setPayee] = useState('')
  const [reference, setReference] = useState('')
  const [amount, setAmount] = useState('')
  const [firstDue, setFirstDue] = useState(today())
  const [count, setCount] = useState('1')
  const [paid, setPaid] = useState(false)
  const [paidOn, setPaidOn] = useState(today())
  const [methodId, setMethodId] = useState('')
  const [accountId, setAccountId] = useState('')
  const alreadyPaid = paid
  const paymentAvailable = canPay && options.can_pay
  const method = options.methods.find(item => String(item.id) === methodId)
  const accounts = method ? options.accounts.filter(account => account.cash_box === (method.kind === 'cash')) : []
  const total = decimal(amount)
  const preview = alreadyPaid || total === null ? [] : paymentSchedule(total, Number(count), firstDue, 'months', 1)
  const validPayment = paymentAvailable && !!method && accounts.some(account => String(account.id) === accountId) &&
    !!paidOn && paidOn <= today() && (method.kind !== 'cash' || paidOn === today())
  const valid = options.expense_categories.some(option => option.value === category) && !!description.trim() &&
    total !== null && total > 0n && (alreadyPaid ? validPayment : preview.length > 0)
  return <form className="erp-finance-form" onChange={onChange} onSubmit={event => {
    event.preventDefault()
    if (!disabled && valid && total !== null) onSubmit({
      category, description: description.trim(), payee: payee.trim(), reference: reference.trim(), total: decimalText(total),
      installment_count: alreadyPaid ? 1 : Number(count), first_due_date: alreadyPaid ? paidOn : firstDue,
      interval_unit: 'months', interval_count: 1,
      ...(alreadyPaid ? {payment: {account_id: Number(accountId), method_id: Number(methodId), paid_on: paidOn}} : {}),
    })
  }}>
    <p>Lance uma conta em aberto ou registre de uma vez uma despesa que já foi paga.</p>
    <fieldset disabled={disabled}>
      <legend>Dados da despesa</legend>
      <label>Categoria<select required value={category} onChange={event => setCategory(event.target.value)}>
        <option value="">Selecione a categoria</option>
        {options.expense_categories.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select></label>
      <label>Descrição<input required maxLength={160} placeholder="Ex.: Aluguel da loja — novembro" value={description} onChange={event => setDescription(event.target.value)} /></label>
      <div className="payable-fields">
        <label>Favorecido (opcional)<input maxLength={140} value={payee} onChange={event => setPayee(event.target.value)} /></label>
        <label>Referência do documento (opcional)<input maxLength={120} value={reference} onChange={event => setReference(event.target.value)} /></label>
        <label>Valor total (R$)<input required inputMode="decimal" placeholder="0,00" value={amount} onChange={event => setAmount(event.target.value)} /></label>
        {!alreadyPaid && <><label>{count === '1' ? 'Vencimento' : 'Primeiro vencimento'}<input required type="date" value={firstDue} onChange={event => setFirstDue(event.target.value)} /></label>
        <label>Parcelas mensais<input required type="number" min={1} max={12} value={count} onChange={event => setCount(event.target.value)} /></label></>}
      </div>
      {(paymentAvailable || alreadyPaid) && <label className="payable-check">
        <input type="checkbox" checked={alreadyPaid} onChange={event => setPaid(event.target.checked)} />
        Já paguei esta despesa
      </label>}
      {alreadyPaid && <fieldset className="payable-expense-payment">
        <legend>Pagamento efetuado</legend>
        {!paymentAvailable && <p className="erp-alert" role="alert">Sem permissão para registrar o pagamento. Desmarque a opção para lançar só a conta em aberto.</p>}
        <div className="payable-fields">
          <label>Forma de pagamento<select aria-label="Forma de pagamento da despesa" required value={methodId} onChange={event => {
            setMethodId(event.target.value); setAccountId('')
          }}>
            <option value="">Selecione</option>
            {options.methods.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select></label>
          <label>Conta de saída<select aria-label="Conta de saída da despesa" required disabled={!method} value={accountId} onChange={event => setAccountId(event.target.value)}>
            <option value="">Selecione</option>
            {accounts.map(account => <option key={account.id} value={account.id}>{account.name}</option>)}
          </select></label>
          <label>Data do pagamento<input required type="date" min={method?.kind === 'cash' ? today() : undefined}
            max={today()} value={paidOn} onChange={event => setPaidOn(event.target.value)} /></label>
        </div>
        {method && accounts.length === 0 && <p className="payable-note">Não há conta ativa compatível com esta forma de pagamento na unidade.</p>}
        {method?.kind === 'cash' && <p className="payable-note">Para pagar em dinheiro, use a data de hoje e um caixa aberto com saldo suficiente.</p>}
        <p className="payable-note">O título será quitado pelo valor total e a saída ficará registrada na conta escolhida. O Lentis não envia dinheiro.</p>
      </fieldset>}
      {preview.length > 0 && <ol className="payable-preview" aria-label="Prévia das parcelas">
        {preview.map((row, index) => <li key={row.date}><span>Parcela {index + 1} · {displayDate(row.date)}</span><strong>R$ {decimalText(row.amount).replace('.', ',')}</strong></li>)}
      </ol>}
      <button type="submit" className="erp-action-button" disabled={disabled || !valid}>{alreadyPaid ? 'Salvar e registrar pagamento' : 'Salvar despesa'}</button>
    </fieldset>
  </form>
}
