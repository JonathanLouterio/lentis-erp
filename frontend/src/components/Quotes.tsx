import FormDialog from './FormDialog'
import './CommercialWindows.css'
import { useQuoteAccess } from '../hooks/useQuoteAccess'
import { useEffect, useState } from 'react'
import { ApiError, getQuoteOptions, getQuote, getQuotes, submitQuoteOperation } from '../api'
import type { AccessibleStore, CashPage, QuoteCustomerChoice, QuoteProductChoice, Quote, QuoteAttempt } from '../api'
import { brl, dateTime, decimal, decimalText, displayDate, failure, today } from './saleMoney'
import './Sales.css'
import './Quotes.css'

type Props = { store: AccessibleStore; userId: number; onSavingChange: (value: boolean) => void; onDirtyChange: (value: boolean) => void; onOpenSale: (id: number) => void }
type Line = { productId: number; name: string; code: string; quantity: string; price: string; discount: string }
const events: Record<string,string> = { created: 'Orçamento criado', updated: 'Proposta revisada', send: 'Proposta pronta', accept: 'Aceite registrado', reject: 'Proposta recusada', convert: 'Convertido em venda' }
function defaultValidity() { const date = new Date(); date.setDate(date.getDate() + 15); return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}` }

export default function Quotes({ store, userId, onSavingChange, onDirtyChange, onOpenSale }: Props) {
  const storageKey = `lentis.quote.${userId}.${store.id}`
  const [rows, setRows] = useState<CashPage<Quote>>({ count: 0, results: [], next: null, previous: null })
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('all')
  const [reload, setReload] = useState(0)
  const [loading, setLoading] = useState(true)
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [catalogError, setCatalogError] = useState('')
  const [customers, setCustomers] = useState<QuoteCustomerChoice[]>([])
  const [products, setProducts] = useState<QuoteProductChoice[]>([])
  const [selected, setSelected] = useState<Quote | null>(null)
  const [editor, setEditor] = useState(false)
  const [customerId, setCustomerId] = useState('')
  const [validity, setValidity] = useState(defaultValidity())
  const [notes, setNotes] = useState('')
  const [discount, setDiscount] = useState('0')
  const [lines, setLines] = useState<Line[]>([])
  const [productId, setProductId] = useState('')
  const [busy, setBusy] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [pending, setPending] = useState<QuoteAttempt | null>(null)
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const rights=useQuoteAccess(store.id,reload)
  const access=rights.access?.actions
  const mayWrite=selected ? !!access?.change && !!selected.actions?.change : !!access?.add
  const closed=!!selected && ['converted','rejected'].includes(selected.status)
  const readOnly=closed || !mayWrite
  const blocked=busy || !!pending || rights.loading || !!rights.error
  const itemValues = lines.map(line => {
    const quantity = decimal(line.quantity, 3), price = decimal(line.price), off = decimal(line.discount)
    const subtotal = quantity !== null && price !== null ? (quantity * price + 500n) / 1000n : 0n
    return { quantity, price, off, subtotal, total: subtotal - (off ?? 0n), valid: quantity !== null && quantity > 0n && quantity <= 999999999999n && price !== null && price <= 999999999999n && off !== null && off <= subtotal && off <= 999999999999n }
  })
  const globalDiscount = decimal(discount)
  const total = itemValues.reduce((sum,item) => sum + item.total, 0n) - (globalDiscount ?? 0n)
  const valid = itemValues.every(item => item.valid) && globalDiscount !== null && globalDiscount <= 999999999999n && total >= 0n && /^\d{4}-\d{2}-\d{2}$/.test(validity) && !catalogLoading && !catalogError
  const expired = validity < today()

  useEffect(() => { onSavingChange(busy); return () => onSavingChange(false) }, [busy, onSavingChange])
  useEffect(() => { onDirtyChange(dirty || !!pending); return () => onDirtyChange(false) }, [dirty, pending, onDirtyChange])
  useEffect(() => {
    if (!dirty && !pending) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }; window.addEventListener('beforeunload',warn)
    return () => window.removeEventListener('beforeunload',warn)
  }, [dirty, pending])
  useEffect(() => { try { const value = sessionStorage.getItem(storageKey); if (value) { setPending(JSON.parse(value) as QuoteAttempt); setEditor(true) } } catch { /* Armazenamento opcional. */ } }, [storageKey])
  useEffect(() => {
    let ignore = false; setLoading(true)
    if(!access?.view){setRows({count:0,results:[],next:null,previous:null});setLoading(false);return}
    void getQuotes(store.id, page, status).then(data => { if (!ignore) setRows(data) }).catch((err: unknown) => { if (!ignore) setError(failure(err)) }).finally(() => { if (!ignore) setLoading(false) })
    return () => { ignore = true }
  }, [store.id,page,status,reload,access?.view])
  useEffect(() => {
    let ignore = false; setCatalogLoading(true); setCatalogError('')
    if(!access?.add && !access?.change){setCustomers([]);setProducts([]);setCatalogLoading(false);return}
    void getQuoteOptions(store.id).then(data => { if (!ignore) { setCustomers(data.customers); setProducts(data.products) } }).catch((err: unknown) => { if (!ignore) setCatalogError(failure(err)) }).finally(() => { if (!ignore) setCatalogLoading(false) })
    return () => { ignore = true }
  }, [store.id,reload,access?.add,access?.change])
  function closeEditor() { setEditor(false); setDirty(false); setSelected(null); setRejecting(false); setReason(''); setError('') }
  function leaveAllowed() { return !blocked && (!dirty || window.confirm('Sair sem salvar as alterações do orçamento?')) }
  function accept(quote: Quote) {
    setSelected(quote); setEditor(true); setCustomerId(quote.customer ? String(quote.customer) : ''); setValidity(quote.valid_until); setNotes(quote.notes); setDiscount(quote.discount_amount)
    setLines(quote.items.map(item => ({ productId: item.product, name: item.product_name, code: item.product_code, quantity: item.quantity, price: item.unit_price, discount: item.discount_amount })))
    setDirty(false); setRejecting(false); setReason(''); setProductId('')
  }
  async function open(id: number) {
    if (!access?.view || !leaveAllowed()) return
    setBusy(true); setError('')
    try { accept(await getQuote(store.id,id)); setSuccess('') } catch (err) { setError(failure(err)) } finally { setBusy(false) }
  }
  function newQuote() {
    if (!access?.add || !leaveAllowed()) return
    setSelected(null); setEditor(true); setCustomerId(''); setValidity(defaultValidity()); setNotes(''); setDiscount('0'); setLines([]); setDirty(false); setError(''); setSuccess(''); setRejecting(false); setReason('')
  }
  function addProduct() {
    const product = products.find(item => String(item.id) === productId)
    if (!product) return
    if (lines.some(line => line.productId === product.id)) { setError('Produto já incluído. Ajuste a quantidade.'); return }
    setLines(items => [...items,{ productId: product.id, name: product.name, code: product.internal_code, quantity: '1', price: product.sale_price, discount: '0' }]); setProductId(''); setDirty(true); setError('')
  }
  function changeLine(index: number, field: 'quantity' | 'price' | 'discount', value: string) { setLines(items => items.map((item, number) => number === index ? {...item,[field]:value} : item)); setDirty(true) }
  async function persist(attempt: QuoteAttempt) {
    const allowed=attempt.action==='save' ? (attempt.quoteId ? access?.change : access?.add) : access?.[attempt.action]
    if (busy || rights.loading || !allowed) return
    setBusy(true); setError('')
    try { sessionStorage.setItem(storageKey,JSON.stringify(attempt)) } catch { /* Mantemos o envio em memória. */ }
    try {
      const quote = await submitQuoteOperation(store.id, attempt)
      accept(quote); if (attempt.action === 'save') closeEditor(); setPending(null); setReload(value => value + 1)
      try { sessionStorage.removeItem(storageKey) } catch { /* Armazenamento opcional. */ }
      setSuccess(attempt.action === 'convert' ? `Venda #${quote.sale} criada em rascunho. ${rights.access?.can_open_sale ? 'Abra a venda para definir o pagamento e concluir.' : 'A conclusão ficará com uma pessoa autorizada a consultar vendas.'}` : attempt.action === 'save' ? 'Orçamento salvo. Nenhum estoque ou recebimento foi movimentado.' : events[attempt.action])
    } catch (err) {
      setError(failure(err))
      if (!(err instanceof ApiError) || err.status === 0 || err.status >= 500) setPending(attempt)
      else { setPending(null); setReload(value => value + 1); try { sessionStorage.removeItem(storageKey) } catch { /* Armazenamento opcional. */ } }
    } finally { setBusy(false) }
  }
  function save() {
    if (!valid || blocked || readOnly) return
    void persist({action:'save',quoteId:selected?.id ?? null,payload:{request_id:crypto.randomUUID(),expected_version:selected?.version,customer_id:customerId?Number(customerId):null,valid_until:validity,notes,discount_amount:decimalText(globalDiscount ?? 0n),items:lines.map((line,index)=>({product_id:line.productId,quantity:decimalText(itemValues[index].quantity ?? 0n,3),unit_price:decimalText(itemValues[index].price ?? 0n),discount_amount:decimalText(itemValues[index].off ?? 0n)}))}})
  }
  function transition(action: 'send' | 'accept' | 'reject' | 'convert') {
    if (!access?.[action] || !selected?.actions?.[action]) return
    if (!selected || blocked || dirty || (action === 'reject' && !reason.trim())) return
    void persist({ action,quoteId:selected.id,payload:{request_id:crypto.randomUUID(),expected_version:selected.version,reason:reason.trim()} })
  }
  if(!access || rights.error || !Object.values(access).some(Boolean))return <section className="erp-card"><p>{rights.error || (rights.loading?'Conferindo permissões de orçamentos…':'Você não tem permissão de operar orçamentos.')}</p><button className="erp-secondary-button" disabled={rights.loading} onClick={()=>setReload(v=>v+1)}>Atualizar acessos</button></section>
  if(selected && !access.view && !mayWrite)return <section className="erp-card"><p role="status">{success || 'Consulta deste orçamento restrita.'}</p>{access.add && <button className="erp-action-button" disabled={blocked} onClick={newQuote}>Novo orçamento</button>}</section>
  return <section className="erp-sales-page erp-quotes-page">
    <div className="erp-page-heading erp-list-heading"><div><span className="erp-kicker">COMERCIAL</span><h1>Orçamentos</h1><p>Propostas da unidade {store.name}. O orçamento não reserva nem baixa estoque.</p></div>{access?.add && <button className="erp-action-button" disabled={blocked || catalogLoading} onClick={newQuote}>Novo orçamento</button>}</div>
    {success && <p className="erp-sales-success" role="status">{success}</p>}{error && <p className="erp-alert" role="alert">{error}</p>}
    {!editor && pending && <div className="erp-card" role="alert"><h2>Conferir o último envio</h2><p>Repita o mesmo envio para recuperar o resultado sem duplicar o orçamento ou a venda.</p><button className="erp-action-button" disabled={busy} onClick={()=>void persist(pending)}>Repetir envio com segurança</button></div>}
    {catalogError && <div className="erp-card"><p className="erp-alert">{catalogError}</p><button className="erp-secondary-button" disabled={blocked} onClick={()=>setReload(value=>value+1)}>Recarregar cadastros</button></div>}
    {!access?.view ? <div className="erp-card"><p>Consulta de orçamentos restrita. Use Novo orçamento se autorizado.</p></div> : <div className="erp-card"><div className="erp-sales-toolbar"><label>Situação<select aria-label="Situação do orçamento" value={status} disabled={blocked} onChange={event=>{setStatus(event.target.value);setPage(1)}}><option value="all">Todas</option><option value="draft">Rascunhos</option><option value="sent">Propostas prontas</option><option value="accepted">Aceitos</option><option value="rejected">Recusados</option><option value="converted">Convertidos</option><option value="expired">Vencidos</option></select></label><button className="erp-secondary-button" disabled={blocked || loading} onClick={()=>setReload(value=>value+1)}>Atualizar orçamentos</button></div>{loading?<p role="status">Carregando orçamentos…</p>:!rows.results.length?<p>Nenhum orçamento encontrado.</p>:<div className="erp-customer-table-wrap"><table className="erp-customer-table"><thead><tr><th>Orçamento</th><th>Cliente</th><th>Situação</th><th>Validade</th><th>Total</th><th>Ação</th></tr></thead><tbody>{rows.results.map(quote=><tr key={quote.id}><td>#{quote.id}</td><td>{quote.customer_name || 'Cliente não identificado'}</td><td>{quote.status_label}{quote.is_expired && <small className="erp-sales-item-name">Validade vencida</small>}</td><td>{displayDate(quote.valid_until)}</td><td>{brl(decimal(quote.total) ?? 0n)}</td><td><button className="erp-table-button" disabled={blocked} onClick={()=>void open(quote.id)}>Abrir orçamento {quote.id}</button></td></tr>)}</tbody></table></div>}<div className="erp-sales-pagination"><button className="erp-secondary-button" disabled={blocked || !rows.previous} onClick={()=>setPage(value=>value-1)}>Anterior</button><span>Página {page} · {rows.count} orçamentos</span><button className="erp-secondary-button" disabled={blocked || !rows.next} onClick={()=>setPage(value=>value+1)}>Próxima</button></div></div>}
    {editor && <FormDialog wide notice={error || success || catalogError} sectionLabel="COMERCIAL · ORÇAMENTOS" title={selected?`Orçamento #${selected.id} · ${selected.status_label}`:'Novo orçamento'} subtitle={store.name} busy={busy || !!pending} dirty={dirty || !!reason} onClose={closeEditor} actions={<>{mayWrite && !closed && <button className="erp-action-button" disabled={blocked || !valid || (!!selected && !dirty)} onClick={save}>{busy?'Salvando…':'Salvar orçamento'}</button>}{access?.send && selected?.actions?.send && <button className="erp-secondary-button" disabled={blocked || dirty || !lines.length || expired} onClick={()=>transition('send')}>Preparar proposta</button>}{access?.accept && selected?.actions?.accept && <button className="erp-action-button" disabled={blocked || dirty || expired} onClick={()=>transition('accept')}>Registrar aceite</button>}{access?.convert && selected?.actions?.convert && <button className="erp-action-button" disabled={blocked || dirty || expired} onClick={()=>transition('convert')}>Converter em venda</button>}</>}>
    {success && <p className="erp-sales-success" role="status">{success}</p>}{error && <p className="erp-alert" role="alert">{error}</p>}
    {pending && <div className="erp-card" role="alert"><h2>Conferir o último envio</h2><p>Repita o mesmo envio para recuperar o resultado sem duplicar o orçamento ou a venda.</p><button className="erp-action-button" disabled={busy} onClick={()=>void persist(pending)}>Repetir envio com segurança</button></div>}
    {catalogError && <div className="erp-card"><p className="erp-alert">{catalogError}</p><button className="erp-secondary-button" disabled={blocked} onClick={()=>setReload(value=>value+1)}>Recarregar cadastros</button></div>}
<div className="erp-checkout-grid">
      <div className="erp-checkout-main"><div className="erp-card"><h2>Cliente e validade</h2><div className="erp-quote-header-fields"><label>Cliente<select aria-label="Cliente do orçamento" value={customerId} disabled={blocked || readOnly || catalogLoading} onChange={event=>{setCustomerId(event.target.value);setDirty(true)}}><option value="">Sem identificação</option>{customerId && !customers.some(item=>String(item.id)===customerId) && <option value={customerId}>{selected?.customer_name || 'Cliente indisponível'}</option>}{customers.map(customer=><option key={customer.id} value={customer.id}>{customer.name}</option>)}</select></label><label>Válido até<input aria-label="Validade do orçamento" type="date" value={validity} disabled={blocked || readOnly} onChange={event=>{setValidity(event.target.value);setDirty(true)}} /></label></div><label>Observações<textarea aria-label="Observações do orçamento" value={notes} maxLength={10000} disabled={blocked || readOnly} onChange={event=>{setNotes(event.target.value);setDirty(true)}} /></label></div>
      <div className="erp-card"><h2>Produtos da proposta</h2>{!readOnly && <div className="erp-quote-product-picker"><label>Produto<select aria-label="Produto do orçamento" value={productId} disabled={blocked || catalogLoading} onChange={event=>setProductId(event.target.value)}><option value="">Selecione</option>{products.map(product=><option key={product.id} value={product.id}>{product.internal_code} · {product.name}</option>)}</select></label><button className="erp-action-button" disabled={blocked || !productId || lines.length>=200} onClick={addProduct}>Adicionar produto</button></div>}{!lines.length && <p>Nenhum produto incluído.</p>}{lines.map((line,index)=><div className="erp-checkout-line" key={line.productId}><div className="erp-checkout-line-name"><strong>{line.name}</strong><small>{line.code}</small></div><div className="erp-checkout-line-fields"><label>Quantidade<input aria-label={`Quantidade do orçamento ${index+1}`} inputMode="decimal" value={line.quantity} disabled={blocked || readOnly} onChange={event=>changeLine(index,'quantity',event.target.value)} /></label><label>Preço (R$)<input aria-label={`Preço do orçamento ${index+1}`} inputMode="decimal" value={line.price} disabled={blocked || readOnly} onChange={event=>changeLine(index,'price',event.target.value)} /></label><label>Desconto (R$)<input aria-label={`Desconto do item ${index+1}`} inputMode="decimal" value={line.discount} disabled={blocked || readOnly} onChange={event=>changeLine(index,'discount',event.target.value)} /></label><strong>{brl(itemValues[index].total)}</strong>{!readOnly && <button className="erp-table-button is-danger" disabled={blocked} onClick={()=>{setLines(items=>items.filter((_,number)=>number!==index));setDirty(true)}}>Remover</button>}</div></div>)}</div>
      {!!selected?.events.length && <div className="erp-card"><h2>Histórico</h2><ol className="erp-sales-history">{selected.events.map(event=><li key={event.id}><strong>{events[event.action] || event.action}</strong><span>{dateTime.format(new Date(event.created_at))} · {event.creator_username}</span>{event.reason && <p>{event.reason}</p>}</li>)}</ol></div>}</div>
      <aside className="erp-card erp-checkout-summary"><span className="erp-kicker">RESUMO DA PROPOSTA</span><h2>{selected?.status_label || 'Rascunho'}</h2><label>Desconto geral (R$)<input aria-label="Desconto geral do orçamento" inputMode="decimal" value={discount} disabled={blocked || readOnly} onChange={event=>{setDiscount(event.target.value);setDirty(true)}} /></label><div className="erp-checkout-grand-total"><span>Total</span><strong>{valid || readOnly ? brl(total) : 'Revisar valores'}</strong></div><p className="erp-sales-hint">Validade: {displayDate(validity)}. O orçamento não autoriza descontos acima do limite do perfil; essa autorização será conferida na venda.</p>{expired && !readOnly && <p className="erp-alert">Validade vencida. Revise a data antes de confirmar a proposta.</p>}{mayWrite && !closed && <>{dirty && selected && <p className="erp-sales-hint">Salvar uma revisão retorna a proposta ao rascunho e exige novo aceite.</p>}</>}{selected && dirty && <p className="erp-sales-hint">Salve as alterações antes de imprimir a proposta.</p>}{access?.reject && selected?.actions?.reject && <button className="erp-secondary-button" disabled={blocked || dirty} onClick={()=>setRejecting(value=>!value)}>Recusar orçamento</button>}{access?.reject && selected?.actions?.reject && rejecting && <><label>Motivo da recusa<textarea aria-label="Motivo da recusa" value={reason} maxLength={255} disabled={blocked} onChange={event=>setReason(event.target.value)} /></label><button className="erp-action-button" disabled={blocked || !reason.trim()} onClick={()=>transition('reject')}>Confirmar recusa</button></>}{selected?.sale && rights.access?.can_open_sale && <><p className="erp-sales-hint">Venda #{selected.sale} criada. A proposta fica preservada; pagamento e conclusão são feitos na venda.</p><button className="erp-action-button" disabled={blocked} onClick={()=>onOpenSale(selected.sale!)}>Abrir venda {selected.sale}</button></>}{selected && dirty && <p className="erp-sales-hint">Salve as alterações antes de imprimir a proposta.</p>}{access?.print && selected?.actions?.print && <button className="erp-secondary-button" disabled={blocked || dirty} onClick={()=>{window.open(`/api/me/quotes/${selected.id}/print/?store_id=${store.id}`,'_blank','noopener,noreferrer')}}>Imprimir / Salvar PDF</button>}{access?.view && selected && <button className="erp-secondary-button" disabled={blocked} onClick={()=>void open(selected.id)}>Reabrir dados atuais</button>}{error && <p className="erp-alert" role="alert">{error}</p>}</aside>
    </div></FormDialog>}
  </section>
}
