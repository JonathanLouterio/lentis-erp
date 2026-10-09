import { useEffect, useState } from 'react'
import { ApiError, cancelSale, getMyCustomers, getMyProducts, getPaymentOptions, getSale, getSales, submitCheckout } from '../api'
import type { AccessibleStore, CheckoutPayload, Customer, PaymentOptions, Product, Sale, SaleStatus, SalesPage } from '../api'
import { brl, dateTime, decimal, decimalText, displayDate, failure, money, paymentSchedule, signedDecimal, today } from './saleMoney'
import CheckoutModal from './CheckoutModal'
import './Sales.css'

type Props = { store: AccessibleStore; userId: number; onSavingChange: (value: boolean) => void; onDirtyChange: (value: boolean) => void }
type Line = { productId: number; name: string; code: string; quantity: string; price: string; discount: string }
type Payment = { key: string; methodId: string; accountId: string; amount: string; auto: boolean; count: number; due: string; confirmed: boolean }
const emptyOptions: PaymentOptions = { methods: [], accounts: [], can_receive: false, allow_negative_stock: false }
const emptyPage: SalesPage = { count: 0, next: null, previous: null, results: [] }
const immediate = ['cash', 'pix', 'transfer']
const credit = ['credit', 'store_credit', 'boleto']

export default function Sales({ store, userId, onSavingChange, onDirtyChange }: Props) {
  const storageKey = `lentis.checkout.${userId}.${store.id}`
  const [sales, setSales] = useState<SalesPage>(emptyPage)
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState<SaleStatus | ''>('')
  const [reload, setReload] = useState(0)
  const [loading, setLoading] = useState(true)
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [catalogError, setCatalogError] = useState('')
  const [customers, setCustomers] = useState<Customer[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const [options, setOptions] = useState<PaymentOptions>(emptyOptions)
  const [selected, setSelected] = useState<Sale | null>(null)
  const [editor, setEditor] = useState(false)
  const [customerId, setCustomerId] = useState('')
  const [notes, setNotes] = useState('')
  const [lines, setLines] = useState<Line[]>([])
  const [discount, setDiscount] = useState('0')
  const [payments, setPayments] = useState<Payment[]>([])
  const [productId, setProductId] = useState('')
  const [search, setSearch] = useState('')
  const [busy, setBusy] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [review, setReview] = useState(false)
  const [cancelOpen, setCancelOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [pending, setPending] = useState<CheckoutPayload | null>(null)
  const readOnly = !!selected && selected.status !== 'draft'
  const blocked = busy || !!pending

  useEffect(() => { onSavingChange(busy); return () => onSavingChange(false) }, [busy, onSavingChange])
  useEffect(() => { onDirtyChange(dirty || !!pending); return () => onDirtyChange(false) }, [dirty, pending, onDirtyChange])
  useEffect(() => {
    if (!dirty && !pending) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty, pending])
  useEffect(() => {
    try {
      const value = sessionStorage.getItem(storageKey)
      if (value) { const recovered = JSON.parse(value) as CheckoutPayload; if (recovered.request_id) { setPending(recovered); setEditor(true) } }
    } catch { /* O navegador pode desabilitar o armazenamento da sessão. */ }
  }, [storageKey])
  useEffect(() => {
    let ignore = false
    setLoading(true)
    void getSales(store.id, page, status).then((data) => { if (!ignore) setSales(data) })
      .catch((err: unknown) => { if (!ignore) setError(failure(err)) }).finally(() => { if (!ignore) setLoading(false) })
    return () => { ignore = true }
  }, [store.id, page, status, reload])
  useEffect(() => {
    let ignore = false
    setCatalogLoading(true); setCatalogError('')
    void Promise.all([getMyCustomers(store.id), getMyProducts(store.id), getPaymentOptions(store.id)])
      .then(([nextCustomers, nextProducts, nextOptions]) => { if (!ignore) { setCustomers(nextCustomers); setProducts(nextProducts); setOptions(nextOptions) } })
      .catch((err: unknown) => { if (!ignore) setCatalogError(failure(err)) }).finally(() => { if (!ignore) setCatalogLoading(false) })
    return () => { ignore = true }
  }, [store.id, reload])

  const values = lines.map((line) => {
    const quantity = decimal(line.quantity, 3), price = decimal(line.price), off = decimal(line.discount)
    const subtotal = quantity !== null && price !== null ? (quantity * price + 500n) / 1000n : 0n
    const valid = quantity !== null && quantity > 0n && quantity <= 999999999999n && price !== null && price <= 999999999999n && off !== null && off <= subtotal && off <= 999999999999n
    return { quantity, price, off, subtotal, total: subtotal - (off ?? 0n), valid }
  })
  const subtotal = values.reduce((sum, item) => sum + item.subtotal, 0n)
  const lineDiscount = values.reduce((sum, item) => sum + (item.off ?? 0n), 0n)
  const globalDiscount = decimal(discount)
  const total = subtotal - lineDiscount - (globalDiscount ?? 0n)
  const itemValid = values.every((item) => item.valid) && globalDiscount !== null && globalDiscount <= 999999999999n && total >= 0n
  const explicitAmount = payments.reduce((sum, payment) => sum + (payment.auto ? 0n : decimal(payment.amount) ?? 0n), 0n)
  const paymentAmounts = payments.map((payment) => payment.auto ? (total > explicitAmount ? total - explicitAmount : 0n) : decimal(payment.amount))
  const allocated = paymentAmounts.reduce<bigint>((sum, amount) => sum + (amount ?? 0n), 0n)
  const received = payments.reduce((sum, payment, index) => sum + (payment.confirmed && immediate.includes(options.methods.find((method) => String(method.id) === payment.methodId)?.kind || '') ? paymentAmounts[index] ?? 0n : 0n), 0n)
  const operator = payments.reduce((sum, payment, index) => sum + (['credit','debit'].includes(options.methods.find((method) => String(method.id) === payment.methodId)?.kind || '') ? paymentAmounts[index] ?? 0n : 0n), 0n)
  const recordedInstallments = selected?.payments?.flatMap((payment) => payment.installments) ?? []
  const receivedSummary = readOnly ? recordedInstallments.reduce((sum,item) => sum + (decimal(item.paid_amount) ?? 0n),0n) : received
  const operatorSummary = readOnly ? recordedInstallments.filter((item) => item.debtor === "operator").reduce((sum,item) => sum + (decimal(item.remaining_amount) ?? 0n),0n) : operator
  const customerSummary = readOnly ? recordedInstallments.filter((item) => item.debtor === "customer").reduce((sum,item) => sum + (decimal(item.remaining_amount) ?? 0n),0n) : allocated - received - operator
  const paymentsValid = payments.every((payment, index) => {
    const amount = paymentAmounts[index], method = options.methods.find((value) => String(value.id) === payment.methodId)
    return amount !== null && amount > 0n && amount <= 999999999999999999n && !!method && options.accounts.some((value) => String(value.id) === payment.accountId) && payment.due.length === 10 && payment.count >= 1 && payment.count <= 12 && amount >= BigInt(payment.count) && (credit.includes(method.kind) || payment.count === 1) && (!payment.confirmed || immediate.includes(method.kind))
  })
  const needsCustomer = payments.some((payment) => ['store_credit','boleto'].includes(options.methods.find((value) => String(value.id) === payment.methodId)?.kind || ''))
  const predictedNegativeStock = lines.flatMap((line,index) => {
    const product = products.find((candidate) => candidate.id === line.productId)
    const before = product ? signedDecimal(product.stock_quantity,3) : null
    const quantity = values[index].quantity
    if (before === null || quantity === null || !values[index].valid || before - quantity >= 0n) return []
    return [{ name: line.name, after: before - quantity }]
  })
  const recordedNegativeStock = selected?.stock_warnings ?? []
  const canComplete = itemValid && lines.length > 0 && paymentsValid && allocated === total && (!needsCustomer || !!customerId) && !catalogLoading && !catalogError && (options.allow_negative_stock || predictedNegativeStock.length === 0)
  const canDraft = itemValid && (paymentsValid || payments.length === 0) && !catalogLoading && !catalogError
  const chosenCustomer = customers.find((customer) => String(customer.id) === customerId)

  function allowedToLeave() { return !blocked && (!dirty || window.confirm('Sair sem salvar as alterações desta venda?')) }
  function accept(sale: Sale) {
    setSelected(sale); setEditor(true); setCustomerId(sale.customer === null ? '' : String(sale.customer)); setNotes(sale.notes)
    setLines(sale.items.map((item) => ({ productId: item.product, name: item.product_name, code: item.product_code, quantity: item.quantity, price: item.unit_price, discount: item.discount_amount })))
    setDiscount(sale.discount_amount || '0')
    setPayments((sale.payments || []).map((payment) => ({ key: crypto.randomUUID(), methodId: String(payment.method), accountId: String(payment.account), amount: payment.amount, auto: false, count: payment.installment_count, due: payment.first_due_date, confirmed: payment.confirmed })))
    setDirty(false); setCancelOpen(false); setReason(''); setReview(false); setProductId('')
  }
  function newSale() {
    if (!allowedToLeave()) return
    setSelected(null); setEditor(true); setLines([]); setPayments([]); setCustomerId(''); setNotes(''); setDiscount('0'); setDirty(false); setError(''); setSuccess(''); setCancelOpen(false); setReason(''); setProductId(''); setSearch('')
  }
  async function openSale(id: number) {
    if (!allowedToLeave()) return
    setBusy(true); setError('')
    try { accept(await getSale(store.id, id)) } catch (err) { setError(failure(err)) } finally { setBusy(false) }
  }
  function changeLine(index: number, field: 'quantity' | 'price' | 'discount', value: string) {
    setLines((items) => items.map((item, number) => number === index ? { ...item, [field]: value } : item)); setDirty(true); setSuccess('')
  }
  function defaultPayment(): Payment {
    const method = options.methods.find((value) => value.kind === 'pix') || options.methods[0]
    const account = options.accounts.find((value) => value.code === 'bank') || options.accounts[0]
    return { key: crypto.randomUUID(), methodId: method ? String(method.id) : '', accountId: account ? String(account.id) : '', amount: '0', auto: true, count: 1, due: today(), confirmed: false }
  }
  function addProduct() {
    const product = products.find((value) => String(value.id) === productId)
    if (!product) return
    if (lines.some((line) => line.productId === product.id)) { setError('Este produto já está na venda. Ajuste a quantidade na lista.'); return }
    setLines((items) => [...items, { productId: product.id, name: product.name, code: product.internal_code, quantity: '1', price: product.sale_price, discount: '0' }])
    if (!payments.length && options.methods.length && options.accounts.length) setPayments([defaultPayment()])
    setProductId(''); setDirty(true); setError(''); setSuccess('')
  }
  function changePayment(key: string, update: Partial<Payment>) { setPayments((items) => items.map((item) => item.key === key ? { ...item, ...update } : item)); setDirty(true); setSuccess('') }
  function addPayment() {
    setPayments((items) => [...items.map((item, index) => ({ ...item, auto: false, amount: decimalText(paymentAmounts[index] ?? 0n) })), defaultPayment()]); setDirty(true)
  }
  function buildPayload(action: 'draft' | 'complete'): CheckoutPayload {
    return { request_id: crypto.randomUUID(), sale_id: selected?.id ?? null, action, customer_id: customerId ? Number(customerId) : null, notes, discount_amount: decimalText(globalDiscount ?? 0n),
      items: lines.map((line, index) => ({ product_id: line.productId, quantity: decimalText(values[index].quantity ?? 0n, 3), unit_price: decimalText(values[index].price ?? 0n), discount_amount: decimalText(values[index].off ?? 0n) })),
      payments: payments.map((payment, index) => ({ method_id: Number(payment.methodId), account_id: Number(payment.accountId), amount: decimalText(paymentAmounts[index] ?? 0n), installment_count: payment.count, first_due_date: payment.due, confirmed: payment.confirmed })),
    }
  }
  async function persist(payload: CheckoutPayload) {
    if (busy) return
    setBusy(true); setError(''); setReview(false)
    try { sessionStorage.setItem(storageKey, JSON.stringify(payload)) } catch { /* O identificador também permanece em memória. */ }
    try {
      const sale = await submitCheckout(store.id, payload)
      setPending(null); try { sessionStorage.removeItem(storageKey) } catch { /* Sem armazenamento disponível. */ }
      accept(sale); setReload((value) => value + 1)
      setSuccess(sale.status === 'completed' ? `Venda #${sale.id} concluída. Estoque e financeiro registrados.` : `Rascunho #${sale.id} salvo. Nenhuma baixa de estoque foi feita.`)
    } catch (err) {
      setError(failure(err))
      if (!(err instanceof ApiError) || err.status === 0 || err.status >= 500) { setPending(payload); setDirty(true) }
      else { setPending(null); try { sessionStorage.removeItem(storageKey) } catch { /* Sem armazenamento disponível. */ } }
    } finally { setBusy(false) }
  }
  async function cancel() {
    if (!selected?.can_cancel || !reason.trim() || blocked) return
    setBusy(true); setError('')
    try { accept(await cancelSale(store.id, selected.id, reason.trim())); setReload((value) => value + 1); setSuccess('Venda cancelada. O estoque foi devolvido e os recebimentos registrados foram estornados no sistema.') }
    catch (err) { setError(failure(err)) } finally { setBusy(false) }
  }

  return <section className="erp-sales-page">
    <div className="erp-page-heading erp-list-heading"><div><span className="erp-kicker">COMERCIAL</span><h1>{editor ? selected ? `Venda #${selected.id}` : 'Nova venda' : 'Vendas'}</h1><p>{editor ? 'Cliente, produtos e pagamento em um único atendimento.' : `Vendas da unidade ${store.name}.`}</p></div>
      {editor ? <button className="erp-secondary-button" disabled={blocked} onClick={() => { if (allowedToLeave()) { setEditor(false); setDirty(false); setSelected(null) } }}>Voltar às vendas</button> : <button className="erp-action-button" disabled={blocked || catalogLoading} onClick={newSale}>Nova venda</button>}
    </div>
    {success && <p className="erp-sales-success" role="status">{success}</p>}
    {error && <p className="erp-alert" role="alert">{error}</p>}
    {pending && <div className="erp-card erp-checkout-recovery" role="alert"><h2>Conferir o último envio</h2><p>A resposta da operação não foi confirmada. Repita o mesmo envio para recuperar o resultado com segurança.</p><button className="erp-action-button" disabled={busy} onClick={() => void persist(pending)}>{busy ? 'Conferindo…' : 'Repetir envio com segurança'}</button></div>}
    {catalogError && <div className="erp-card"><p className="erp-alert">{catalogError}</p><button className="erp-secondary-button" disabled={blocked} onClick={() => setReload((value) => value + 1)}>Recarregar cadastros</button></div>}
    {!editor ? <div className="erp-card erp-sales-list">
      <div className="erp-sales-toolbar"><label>Situação<select aria-label="Situação" value={status} disabled={blocked} onChange={(event) => { setStatus(event.target.value as SaleStatus | ''); setPage(1) }}><option value="">Todas</option><option value="draft">Rascunhos</option><option value="completed">Finalizadas</option><option value="cancelled">Canceladas</option></select></label><span>{sales.count} vendas</span><button className="erp-secondary-button" disabled={blocked || loading} onClick={() => setReload((value) => value + 1)}>Atualizar lista</button></div>
      {loading ? <p role="status">Carregando vendas…</p> : !sales.results.length ? <p>Nenhuma venda encontrada.</p> : <div className="erp-customer-table-wrap"><table className="erp-customer-table"><thead><tr><th>Venda</th><th>Data</th><th>Cliente</th><th>Situação</th><th>Total</th><th>Ação</th></tr></thead><tbody>{sales.results.map((sale) => <tr key={sale.id}><td>#{sale.id}</td><td>{dateTime.format(new Date(sale.created_at))}</td><td>{sale.customer_name || 'Venda balcão'}</td><td><span className={`erp-sale-badge is-${sale.status}`}>{sale.status_label}</span></td><td>{money.format(Number(sale.total))}</td><td><button className="erp-table-button" disabled={blocked} onClick={() => void openSale(sale.id)}>Abrir venda {sale.id}</button></td></tr>)}</tbody></table></div>}
      <div className="erp-sales-pagination"><button className="erp-secondary-button" disabled={blocked || loading || !sales.previous} onClick={() => setPage((value) => value - 1)}>Anterior</button><span>Página {page}</span><button className="erp-secondary-button" disabled={blocked || loading || !sales.next} onClick={() => setPage((value) => value + 1)}>Próxima</button></div>
    </div> : !pending && <div className="erp-checkout-grid" aria-busy={busy}>
      <div className="erp-checkout-main">
        <div className="erp-card"><div className="erp-checkout-section"><span>01</span><h2>Cliente</h2>{readOnly && <span className={`erp-sale-badge is-${selected?.status}`}>{selected?.status_label}</span>}</div>
          <label>Cliente da venda<select aria-label="Cliente da venda" value={customerId} disabled={blocked || readOnly || catalogLoading} onChange={(event) => { setCustomerId(event.target.value); setDirty(true) }}><option value="">Venda balcão (sem identificação)</option>{customerId && !chosenCustomer && <option value={customerId}>{selected?.customer_name || 'Cliente indisponível'}</option>}{customers.map((customer) => <option key={customer.id} value={customer.id}>{customer.name}{customer.cpf ? ` · ${customer.cpf}` : customer.cnpj ? ` · ${customer.cnpj}` : ''}</option>)}</select></label>
          {needsCustomer && !customerId && <p className="erp-alert">Selecione um cliente para boleto ou crediário.</p>}
          <details className="erp-checkout-notes" open={!!notes || undefined}><summary>Observações do atendimento</summary><label>Observações<textarea aria-label="Observações" value={notes} disabled={blocked || readOnly} maxLength={10000} onChange={(event) => { setNotes(event.target.value); setDirty(true) }} placeholder="Informações úteis para este atendimento" /></label></details>
        </div>
        <div className="erp-card"><div className="erp-checkout-section"><span>02</span><h2>Produtos</h2><small>{lines.length} itens</small></div>
          {!readOnly && <div className="erp-checkout-product-picker"><label>Buscar produto<input aria-label="Buscar produto" value={search} disabled={blocked || catalogLoading} onChange={(event) => setSearch(event.target.value)} placeholder="Nome, código ou código de barras" /></label><label>Produto<select aria-label="Produto" value={productId} disabled={blocked || catalogLoading} onChange={(event) => setProductId(event.target.value)}><option value="">Selecione um produto</option>{products.filter((product) => `${product.name} ${product.internal_code} ${product.barcode}`.toLocaleLowerCase('pt-BR').includes(search.toLocaleLowerCase('pt-BR'))).map((product) => <option key={product.id} value={product.id}>{product.internal_code} · {product.name} · {money.format(Number(product.sale_price))}</option>)}</select></label><button className="erp-action-button" disabled={blocked || !productId || catalogLoading || !!catalogError} onClick={addProduct}>Adicionar</button></div>}
          {!lines.length ? <div className="erp-checkout-empty">Adicione os produtos que o cliente está levando.</div> : <div className="erp-checkout-lines">{lines.map((line, index) => <div className="erp-checkout-line" key={line.productId}>
            <div className="erp-checkout-line-name"><strong>{line.name}</strong><small>{line.code}{!readOnly && ` · Estoque: ${products.find((product) => product.id === line.productId)?.stock_quantity ?? 'indisponível'}`}</small></div>
            <div className="erp-checkout-line-fields"><label>Quantidade<input aria-label={`Quantidade de ${line.name}`} inputMode="decimal" value={line.quantity} disabled={blocked || readOnly} onChange={(event) => changeLine(index,'quantity',event.target.value)} /></label><label>Preço (R$)<input aria-label={`Preço de ${line.name}`} inputMode="decimal" value={line.price} disabled={blocked || readOnly} onChange={(event) => changeLine(index,'price',event.target.value)} /></label><label>Desconto (R$)<input aria-label={`Desconto de ${line.name}`} inputMode="decimal" value={line.discount} disabled={blocked || readOnly} onChange={(event) => changeLine(index,'discount',event.target.value)} /></label><strong>{values[index].valid ? brl(values[index].total) : 'Valor inválido'}</strong>{!readOnly && <button className="erp-table-button is-danger" aria-label={`Remover ${line.name}`} disabled={blocked} onClick={() => { setLines((items) => items.filter((_, number) => number !== index)); setDirty(true) }}>Remover</button>}</div>
          </div>)}</div>}
        </div>
        <div className="erp-card"><div className="erp-checkout-section"><span>03</span><h2>Pagamento</h2><small>Combine formas e condições</small></div>
          {!options.methods.length || !options.accounts.length ? <p className="erp-alert">Configure as formas de pagamento e contas de recebimento antes de concluir a venda.</p> : null}
          {payments.map((payment, index) => {
            const method = options.methods.find((value) => String(value.id) === payment.methodId)
            const amount = paymentAmounts[index] ?? 0n
            const schedule = paymentSchedule(amount, payment.count, payment.due)
            return <div className="erp-checkout-payment" key={payment.key}>
              <div className="erp-checkout-payment-title"><strong>Pagamento {index + 1}</strong>{!readOnly && <button className="erp-table-button is-danger" disabled={blocked} onClick={() => { setPayments((items) => items.filter((item) => item.key !== payment.key)); setDirty(true) }}>Remover pagamento {index + 1}</button>}</div>
              <div className="erp-checkout-payment-fields"><label>Forma<select aria-label={`Forma ${index+1}`} value={payment.methodId} disabled={blocked || readOnly} onChange={(event) => { const next = options.methods.find((value) => String(value.id) === event.target.value); changePayment(payment.key, { methodId: event.target.value, count: 1, confirmed: false, ...(next?.kind === 'cash' ? { accountId: String(options.accounts.find((value) => value.code === 'cash')?.id || options.accounts[0]?.id || '') } : {}) }) }}><option value="">Selecione</option>{readOnly && !method && <option value={payment.methodId}>{selected?.payments[index]?.method_name || 'Forma registrada'}</option>}{options.methods.map((value) => <option key={value.id} value={value.id}>{value.name}</option>)}</select></label>
                <label>Valor (R$)<input aria-label={`Valor do pagamento ${index+1}`} inputMode="decimal" value={payment.auto ? decimalText(amount) : payment.amount} disabled={blocked || readOnly} onChange={(event) => changePayment(payment.key,{ amount: event.target.value, auto: false })} /></label>
                <label>Conta de recebimento<select aria-label={`Conta ${index+1}`} value={payment.accountId} disabled={blocked || readOnly} onChange={(event) => changePayment(payment.key,{accountId:event.target.value})}>{readOnly && !options.accounts.some((value) => String(value.id) === payment.accountId) && <option value={payment.accountId}>{selected?.payments[index]?.account_name || 'Conta registrada'}</option>}<option value="">Selecione</option>{options.accounts.map((value) => <option key={value.id} value={value.id}>{value.name}</option>)}</select></label>
              </div>
              <div className="erp-checkout-payment-extra"><label>Parcelas<select aria-label={`Parcelas ${index+1}`} value={payment.count} disabled={blocked || readOnly || !credit.includes(method?.kind || selected?.payments[index]?.kind || '')} onChange={(event) => changePayment(payment.key,{ count: Number(event.target.value) })}>{Array.from({length:12},(_,i) => <option key={i} value={i+1}>{i+1}x sem juros</option>)}</select></label><label>{['credit','debit'].includes(method?.kind || '') ? 'Primeiro repasse previsto' : 'Primeiro vencimento'}<input aria-label={`Vencimento ${index+1}`} type="date" value={payment.due} disabled={blocked || readOnly} onChange={(event) => changePayment(payment.key,{due:event.target.value})} /></label>
                {immediate.includes(method?.kind || selected?.payments[index]?.kind || '') ? <label className="erp-checkout-checkbox"><input type="checkbox" aria-label={`Recebido agora ${index+1}`} checked={payment.confirmed} disabled={blocked || readOnly} onChange={(event) => changePayment(payment.key,{confirmed:event.target.checked})} />Recebimento confirmado</label> : <p className="erp-sales-hint">{['credit','debit'].includes(method?.kind || selected?.payments[index]?.kind || '') ? 'Repasse da operadora a receber.' : 'Parcelas a receber do cliente.'}</p>}
              </div>
              {schedule.length > 0 && <div className="erp-checkout-installments" aria-label={`Prévia das parcelas ${index+1}`}>{schedule.map((installment, number) => <span key={number}><strong>{number+1}/{payment.count} · {brl(installment.amount)}</strong><small>{displayDate(installment.date)}</small></span>)}</div>}
              {readOnly && selected?.payments[index]?.installments.map((installment) => <p className="erp-sales-hint" key={installment.id}>Parcela {installment.number}: {installment.status === 'cancelled' ? 'Cancelada' : `Recebido ${money.format(Number(installment.paid_amount))} · Saldo ${money.format(Number(installment.remaining_amount))}`}</p>)}
            </div>
          })}
          {!!payments.length && !paymentsValid && !readOnly && <p className="erp-alert" role="alert">Confira a forma, a conta, o valor positivo e o vencimento de cada pagamento. Cada parcela deve ter pelo menos um centavo.</p>}
          {!payments.length && <p className="erp-sales-hint">Defina como o valor será pago. Uma entrada pode usar Pix e o restante, crediário.</p>}
          {!readOnly && <button className="erp-secondary-button" disabled={blocked || catalogLoading || !options.methods.length || !options.accounts.length || payments.length >= 20} onClick={addPayment}>+ Adicionar forma de pagamento</button>}
          {selected?.financial_status === 'legacy' && <p className="erp-alert">Esta venda foi registrada antes do financeiro. Nenhum recebimento foi presumido para ela.</p>}
        </div>
        {selected?.events.length ? <div className="erp-card"><h2>Histórico da venda</h2><ol className="erp-sales-history">{selected.events.map((event) => <li key={event.id}><strong>{event.event_label}</strong><span>{dateTime.format(new Date(event.created_at))} · {event.creator_username}</span>{event.reason && <p>{event.reason}</p>}</li>)}</ol></div> : null}
      </div>
      <aside className="erp-card erp-checkout-summary"><span className="erp-kicker">RESUMO DO ATENDIMENTO</span><h2>{chosenCustomer?.name || selected?.customer_name || 'Venda balcão'}</h2><p className="erp-sales-hint">{store.name} · {lines.length} itens</p>
        <dl className="erp-sales-totals"><div><dt>Subtotal</dt><dd>{brl(subtotal)}</dd></div><div><dt>Descontos dos itens</dt><dd>{brl(lineDiscount)}</dd></div></dl>
        <label>Desconto da venda (R$)<input aria-label="Desconto da venda" inputMode="decimal" value={discount} disabled={blocked || readOnly} onChange={(event) => { setDiscount(event.target.value); setDirty(true) }} /></label>
        <div className="erp-checkout-grand-total"><span>Total da venda</span><strong>{itemValid ? brl(total) : 'Revisar valores'}</strong></div>
        <dl className="erp-sales-totals erp-checkout-financial-summary"><div><dt>{readOnly ? "Recebido no sistema" : "Recebido na venda"}</dt><dd>{brl(receivedSummary)}</dd></div><div><dt>A receber do cliente</dt><dd>{brl(customerSummary)}</dd></div><div><dt>A receber da operadora</dt><dd>{brl(operatorSummary)}</dd></div>{!readOnly && <div className={allocated === total ? 'is-balanced' : 'is-unbalanced'}><dt>{allocated > total ? 'Valor excedente' : 'Falta distribuir'}</dt><dd>{brl(allocated > total ? allocated-total : total-allocated)}</dd></div>}</dl>
        {((!readOnly && predictedNegativeStock.length > 0) || (readOnly && recordedNegativeStock.length > 0)) && <div className="erp-sales-warning" role="status"><strong>{readOnly ? 'Esta venda deixou produtos com estoque negativo.' : options.allow_negative_stock ? 'A venda poderá ser concluída com estoque negativo.' : 'Esta unidade bloqueia vendas com estoque negativo.'}</strong><ul>{readOnly ? recordedNegativeStock.map((item) => <li key={item.product}>{item.product_name}: saldo após a venda {Number(item.balance_after).toLocaleString('pt-BR',{maximumFractionDigits:3})}</li>) : predictedNegativeStock.map((item) => <li key={item.name}>{item.name}: saldo previsto {(Number(item.after)/1000).toLocaleString("pt-BR",{maximumFractionDigits:3})}</li>)}</ul></div>}
        {error && <p className="erp-alert" role="alert">{error}</p>}
        {!readOnly && <><button className="erp-action-button" disabled={blocked || !canComplete} onClick={() => setReview(true)}>{busy ? 'Registrando…' : 'Concluir venda'}</button><button className="erp-secondary-button" disabled={blocked || !canDraft} onClick={() => void persist(buildPayload('draft'))}>Salvar rascunho</button><p className="erp-sales-hint">O rascunho mantém o atendimento sem baixar o estoque.</p></>}
        {selected?.status === 'cancelled' && <p className="erp-alert">Venda cancelada: {selected.cancellation_reason}</p>}
        {selected?.can_cancel && <button className="erp-table-button is-danger" disabled={blocked} onClick={() => setCancelOpen((value) => !value)}>Cancelar venda</button>}
        {cancelOpen && <div className="erp-checkout-cancel"><label>Motivo do cancelamento<textarea aria-label="Motivo do cancelamento" maxLength={255} value={reason} disabled={blocked} onChange={(event) => setReason(event.target.value)} /></label><p className="erp-sales-hint">Os recebimentos serão estornados no registro do sistema. Uma devolução de dinheiro ao cliente deve ser realizada e conferida separadamente.</p><button className="erp-action-button" disabled={blocked || !reason.trim()} onClick={() => void cancel()}>Confirmar cancelamento</button></div>}
      </aside>
    </div>}
    {review && <CheckoutModal titleId="checkout-review-title" busy={busy} onClose={() => setReview(false)}><div className="erp-card erp-checkout-modal"><span className="erp-kicker">CONFERÊNCIA</span><h2 id="checkout-review-title">Conferir e concluir</h2><p>{chosenCustomer?.name || 'Venda balcão'} · {store.name}</p><strong className="erp-checkout-review-total">{brl(total)}</strong><p>{lines.length} itens · Recebido agora: {brl(received)}</p>{payments.map((payment,index) => <p key={payment.key}>{options.methods.find((value) => String(value.id) === payment.methodId)?.name}: {brl(paymentAmounts[index] ?? 0n)} em {payment.count}x</p>)}{predictedNegativeStock.length > 0 && <div className="erp-sales-warning" role="status"><strong>Atenção: estoque negativo</strong><ul>{predictedNegativeStock.map((item) => <li key={item.name}>{item.name}: saldo previsto {(Number(item.after)/1000).toLocaleString("pt-BR",{maximumFractionDigits:3})}</li>)}</ul><p>A venda será registrada e este saldo ficará no histórico.</p></div>}<p className="erp-sales-hint">Ao confirmar, a venda será concluída com a baixa do estoque e o registro financeiro.</p><div className="erp-sales-actions"><button className="erp-secondary-button" autoFocus onClick={() => setReview(false)}>Voltar à edição</button><button className="erp-action-button" disabled={busy || !canComplete} onClick={() => void persist(buildPayload('complete'))}>Confirmar venda</button></div></div></CheckoutModal>}
  </section>
}
