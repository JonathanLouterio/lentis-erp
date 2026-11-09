import FormDialog from './FormDialog'
import './CommercialWindows.css'
import { useQuoteAccess } from '../hooks/useQuoteAccess'
import { useEffect, useState } from 'react'
import { ApiError, getQuoteOptions, getQuote, getQuotes, submitQuoteOperation } from '../api'
import type { AccessibleStore, QuotePage, QuoteCustomerChoice, QuoteProductChoice, Quote, QuoteAttempt, QuoteLossCategory, QuoteLossFilter } from '../api'
import { brl, dateTime, decimal, decimalText, displayDate, failure, today } from './saleMoney'
import './Sales.css'
import './Quotes.css'

type Props = { store: AccessibleStore; userId: number; onSavingChange: (value: boolean) => void; onDirtyChange: (value: boolean) => void; onOpenSale: (id: number) => void }
type Line = { productId: number; name: string; code: string; quantity: string; price: string; discount: string }
const events: Record<string,string> = { created: 'Orçamento criado', updated: 'Proposta revisada', send: 'Proposta pronta', accept: 'Aceite registrado', reject: 'Perda registrada', convert: 'Convertido em venda', contact: 'Contato registrado', schedule: 'Retorno agendado' }
const lossLabels:Record<QuoteLossCategory|'',string>={price:'Preço',deadline:'Prazo',no_response:'Sem resposta',other:'Outro','':'Sem categoria'}
const lossCategories:QuoteLossCategory[]=['price','deadline','no_response','other']
function defaultValidity() { const date = new Date(); date.setDate(date.getDate() + 15); return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}` }

export default function Quotes({ store, userId, onSavingChange, onDirtyChange, onOpenSale }: Props) {
  const storageKey = `lentis.quote.${userId}.${store.id}`
  const [rows, setRows] = useState<QuotePage>({ count: 0, results: [], next: null, previous: null })
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('all')
  const [dueOnly,setDueOnly] = useState(false)
  const [lossFilter,setLossFilter] = useState<QuoteLossFilter>()
  const [lossCategory,setLossCategory] = useState<QuoteLossCategory|''>('')
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
  const [followupOpen,setFollowupOpen] = useState(false)
  const [followupKind,setFollowupKind] = useState<'contact'|'schedule'>('contact')
  const [followupDate,setFollowupDate] = useState('')
  const [followupNote,setFollowupNote] = useState('')
  const rights=useQuoteAccess(store.id,reload)
  const access=rights.access?.actions
  const mayWrite=selected ? !!access?.change && !!selected.actions?.change : !!access?.add
  const closed=!!selected && ['converted','rejected'].includes(selected.status)
  const readOnly=closed || !mayWrite
  const blocked=busy || !!pending || rights.loading || !!rights.error
  const unsaved=dirty || followupOpen || !!lossCategory || !!reason
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
  useEffect(() => { onDirtyChange(unsaved || !!pending); return () => onDirtyChange(false) }, [unsaved, pending, onDirtyChange])
  useEffect(() => {
    if (!unsaved && !pending) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }; window.addEventListener('beforeunload',warn)
    return () => window.removeEventListener('beforeunload',warn)
  }, [unsaved, pending])
  useEffect(() => { try { const value = sessionStorage.getItem(storageKey); if (value) { setPending(JSON.parse(value) as QuoteAttempt); setEditor(true) } } catch { /* Armazenamento opcional. */ } }, [storageKey])
  useEffect(() => {
    let ignore = false; setLoading(true)
    if(!access?.view){setRows({count:0,results:[],next:null,previous:null});setLoading(false);return}
    void getQuotes(store.id, page, status, dueOnly, lossFilter).then(data => { if (!ignore) setRows(data) }).catch((err: unknown) => { if (!ignore) setError(failure(err)) }).finally(() => { if (!ignore) setLoading(false) })
    return () => { ignore = true }
  }, [store.id,page,status,dueOnly,lossFilter,reload,access?.view])
  useEffect(() => {
    let ignore = false; setCatalogLoading(true); setCatalogError('')
    if(!access?.add && !access?.change){setCustomers([]);setProducts([]);setCatalogLoading(false);return}
    void getQuoteOptions(store.id).then(data => { if (!ignore) { setCustomers(data.customers); setProducts(data.products) } }).catch((err: unknown) => { if (!ignore) setCatalogError(failure(err)) }).finally(() => { if (!ignore) setCatalogLoading(false) })
    return () => { ignore = true }
  }, [store.id,reload,access?.add,access?.change])
  function resetFollowup() {
    setFollowupOpen(false); setFollowupKind('contact'); setFollowupDate(''); setFollowupNote('')
  }
  function closeEditor() { resetFollowup(); setEditor(false); setDirty(false); setSelected(null); setRejecting(false); setLossCategory(''); setReason(''); setError('') }
  function leaveAllowed() { return !blocked && (!unsaved || window.confirm('Sair sem salvar as alterações do orçamento?')) }
  function accept(quote: Quote) {
    resetFollowup(); setSelected(quote); setEditor(true); setCustomerId(quote.customer ? String(quote.customer) : ''); setValidity(quote.valid_until); setNotes(quote.notes); setDiscount(quote.discount_amount)
    setLines(quote.items.map(item => ({ productId: item.product, name: item.product_name, code: item.product_code, quantity: item.quantity, price: item.unit_price, discount: item.discount_amount })))
    setDirty(false); setRejecting(false); setLossCategory(''); setReason(''); setProductId('')
  }
  async function open(id: number) {
    if (!access?.view || !leaveAllowed()) return
    setBusy(true); setError('')
    try { accept(await getQuote(store.id,id)); setSuccess('') } catch (err) { setError(failure(err)) } finally { setBusy(false) }
  }
  function newQuote() {
    if (!access?.add || !leaveAllowed()) return
    resetFollowup(); setSelected(null); setEditor(true); setCustomerId(''); setValidity(defaultValidity()); setNotes(''); setDiscount('0'); setLines([]); setDirty(false); setError(''); setSuccess(''); setRejecting(false); setLossCategory(''); setReason('')
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
      accept(quote); if (attempt.action === 'save') closeEditor(); setPending(null); if(dueOnly)setPage(1); setReload(value => value + 1)
      try { sessionStorage.removeItem(storageKey) } catch { /* Armazenamento opcional. */ }
      setSuccess(attempt.action === 'convert' ? `Venda #${quote.sale} criada em rascunho. ${rights.access?.can_open_sale ? 'Abra a venda para definir o pagamento e concluir.' : 'A conclusão ficará com uma pessoa autorizada a consultar vendas.'}` : attempt.action === 'save' ? 'Orçamento salvo. Nenhum estoque ou recebimento foi movimentado.' : attempt.action === 'followup' ? events[attempt.payload.kind] : events[attempt.action])
    } catch (err) {
      setError(failure(err))
      if (!(err instanceof ApiError) || err.status === 0 || err.status >= 500) setPending(attempt)
      else { setPending(null); if(dueOnly)setPage(1); setReload(value => value + 1); try { sessionStorage.removeItem(storageKey) } catch { /* Armazenamento opcional. */ } }
    } finally { setBusy(false) }
  }
  function save() {
    if (!valid || blocked || readOnly || followupOpen || rejecting) return
    void persist({action:'save',quoteId:selected?.id ?? null,payload:{request_id:crypto.randomUUID(),expected_version:selected?.version,customer_id:customerId?Number(customerId):null,valid_until:validity,notes,discount_amount:decimalText(globalDiscount ?? 0n),items:lines.map((line,index)=>({product_id:line.productId,quantity:decimalText(itemValues[index].quantity ?? 0n,3),unit_price:decimalText(itemValues[index].price ?? 0n),discount_amount:decimalText(itemValues[index].off ?? 0n)}))}})
  }
  function transition(action: 'send' | 'accept' | 'reject' | 'convert') {
    if (!access?.[action] || !selected?.actions?.[action]) return
    if (!selected || blocked || dirty || followupOpen || (rejecting && action!=='reject')) return
    const payload={request_id:crypto.randomUUID(),expected_version:selected.version,reason:reason.trim()}
    if(action==='reject'){
      if(!lossCategory||(lossCategory==='other'&&!payload.reason))return
      void persist({action,quoteId:selected.id,payload:{...payload,loss_category:lossCategory}})
    }else void persist({action,quoteId:selected.id,payload})
  }
  function registerFollowup() {
    if(!selected?.actions.followup || !access?.followup || blocked || dirty || (followupKind==='schedule' && !followupDate))return
    void persist({action:'followup',quoteId:selected.id,payload:{
      request_id:crypto.randomUUID(),expected_version:selected.version,kind:followupKind,
      next_contact_on:followupDate||null,reason:followupNote.trim(),
    }})
  }
  if(!access || rights.error || !Object.values(access).some(Boolean))return <section className="erp-card"><p>{rights.error || (rights.loading?'Conferindo permissões de orçamentos…':'Você não tem permissão de operar orçamentos.')}</p><button className="erp-secondary-button" disabled={rights.loading} onClick={()=>setReload(v=>v+1)}>Atualizar acessos</button></section>
  if(selected && !access.view && !mayWrite)return <section className="erp-card"><p role="status">{success || 'Consulta deste orçamento restrita.'}</p>{access.add && <button className="erp-action-button" disabled={blocked} onClick={newQuote}>Novo orçamento</button>}</section>
  return <section className="erp-sales-page erp-quotes-page">
    <div className="erp-page-heading erp-list-heading"><div><span className="erp-kicker">COMERCIAL</span><h1>Orçamentos</h1><p>Propostas da unidade {store.name}. O orçamento não reserva nem baixa estoque.</p></div>{access?.add && <button className="erp-action-button" disabled={blocked || catalogLoading} onClick={newQuote}>Novo orçamento</button>}</div>
    {success && <p className="erp-sales-success" role="status">{success}</p>}{error && <p className="erp-alert" role="alert">{error}</p>}
    {!editor && pending && <div className="erp-card" role="alert"><h2>Conferir o último envio</h2><p>Repita o mesmo envio para recuperar o resultado sem duplicar o orçamento ou a venda.</p><button className="erp-action-button" disabled={busy} onClick={()=>void persist(pending)}>Repetir envio com segurança</button></div>}
    {catalogError && <div className="erp-card"><p className="erp-alert">{catalogError}</p><button className="erp-secondary-button" disabled={blocked} onClick={()=>setReload(value=>value+1)}>Recarregar cadastros</button></div>}
    {!access?.view ? <div className="erp-card"><p>Consulta de orçamentos restrita. Use Novo orçamento se autorizado.</p></div> : <div className="erp-card"><div className="erp-sales-toolbar"><label>Situação<select aria-label="Situação do orçamento" value={status} disabled={blocked || dueOnly} onChange={event=>{setStatus(event.target.value);setLossFilter(undefined);setPage(1)}}><option value="all">Todas</option><option value="draft">Rascunhos</option><option value="sent">Propostas prontas</option><option value="accepted">Aceitos</option><option value="rejected">Recusados</option><option value="converted">Convertidos</option><option value="expired">Vencidos</option></select></label><button type="button" className={dueOnly?'erp-action-button':'erp-secondary-button'} aria-pressed={dueOnly} disabled={blocked} onClick={()=>{setDueOnly(!dueOnly);setLossFilter(undefined);setPage(1);setStatus('all')}}>Retornar hoje</button><button className="erp-secondary-button" disabled={blocked || loading} onClick={()=>setReload(value=>value+1)}>Atualizar orçamentos</button></div>
    {status==='rejected'&&!dueOnly&&rows.loss_summary&&<section className="erp-quote-loss-summary" aria-labelledby="quote-loss-summary-title">
      <h2 id="quote-loss-summary-title">Perdas por motivo</h2>
      <p>Todo o histórico de orçamentos recusados desta unidade.</p>
      <div className="erp-quote-loss-filters">
        <button type="button" className="erp-secondary-button" aria-pressed={!lossFilter} disabled={blocked} onClick={()=>{setLossFilter(undefined);setPage(1)}}>
          Todas as perdas <strong>{rows.loss_summary.reduce((sum,item)=>sum+item.count,0)}</strong>
        </button>
        {rows.loss_summary.map(item=>{
          const key=item.category||'uncategorized'
          return <button type="button" key={key} className="erp-secondary-button" aria-pressed={lossFilter===key} disabled={blocked} onClick={()=>{setLossFilter(key);setPage(1)}}>
            {lossLabels[item.category]} <strong>{item.count}</strong>
          </button>
        })}
      </div>
    </section>}
    {loading?<p role="status">Carregando orçamentos…</p>:!rows.results.length?<p>{dueOnly?'Nenhum retorno para hoje ou em atraso.':'Nenhum orçamento encontrado.'}</p>:<div className="erp-customer-table-wrap"><table className="erp-customer-table"><thead><tr><th>Orçamento</th><th>Cliente</th><th>Situação</th><th>Validade</th><th>Total</th><th>Ação</th></tr></thead><tbody>{rows.results.map(quote=><tr key={quote.id}><td>#{quote.id}</td><td>{quote.customer_name || 'Cliente não identificado'}{quote.next_contact_on&&<small className="erp-sales-item-name">Retorno: {displayDate(quote.next_contact_on)}</small>}</td><td>{quote.status_label}{quote.status==='rejected'&&<small className="erp-sales-item-name">{lossLabels[quote.loss_category]}</small>}{quote.is_expired && <small className="erp-sales-item-name">Validade vencida</small>}</td><td>{displayDate(quote.valid_until)}</td><td>{brl(decimal(quote.total) ?? 0n)}</td><td><button className="erp-table-button" disabled={blocked} onClick={()=>void open(quote.id)}>Abrir orçamento {quote.id}</button></td></tr>)}</tbody></table></div>}<div className="erp-sales-pagination"><button className="erp-secondary-button" disabled={blocked || !rows.previous} onClick={()=>setPage(value=>value-1)}>Anterior</button><span>Página {page} · {rows.count} orçamentos</span><button className="erp-secondary-button" disabled={blocked || !rows.next} onClick={()=>setPage(value=>value+1)}>Próxima</button></div></div>}
    {editor && <FormDialog wide notice={error || success || catalogError} sectionLabel="COMERCIAL · ORÇAMENTOS" title={selected?`Orçamento #${selected.id} · ${selected.status_label}`:'Novo orçamento'} subtitle={store.name} busy={busy || !!pending} dirty={unsaved} onClose={closeEditor} actions={<>{mayWrite && !closed && <button className="erp-action-button" disabled={blocked || followupOpen || rejecting || !valid || (!!selected && !dirty)} onClick={save}>{busy?'Salvando…':'Salvar orçamento'}</button>}{access?.send && selected?.actions?.send && <button className="erp-secondary-button" disabled={blocked || followupOpen || rejecting || dirty || !lines.length || expired} onClick={()=>transition('send')}>Preparar proposta</button>}{access?.accept && selected?.actions?.accept && <button className="erp-action-button" disabled={blocked || followupOpen || rejecting || dirty || expired} onClick={()=>transition('accept')}>Registrar aceite</button>}{access?.convert && selected?.actions?.convert && <button className="erp-action-button" disabled={blocked || followupOpen || rejecting || dirty || expired} onClick={()=>transition('convert')}>Converter em venda</button>}</>}>
    {success && <p className="erp-sales-success" role="status">{success}</p>}{error && <p className="erp-alert" role="alert">{error}</p>}
    {pending && <div className="erp-card" role="alert"><h2>Conferir o último envio</h2><p>Repita o mesmo envio para recuperar o resultado sem duplicar o orçamento ou a venda.</p><button className="erp-action-button" disabled={busy} onClick={()=>void persist(pending)}>Repetir envio com segurança</button></div>}
    {catalogError && <div className="erp-card"><p className="erp-alert">{catalogError}</p><button className="erp-secondary-button" disabled={blocked} onClick={()=>setReload(value=>value+1)}>Recarregar cadastros</button></div>}
<div className="erp-checkout-grid">
      <div className="erp-checkout-main">
      {selected&&(selected.status==='sent'||selected.last_contact)&&<section className="erp-card erp-quote-followup" aria-labelledby="quote-followup-title">
        <h2 id="quote-followup-title">Acompanhamento</h2>
        <dl><div><dt>Último contato</dt><dd>{selected.last_contact?`${dateTime.format(new Date(selected.last_contact.created_at))} · ${selected.last_contact.creator_username}`:'Nenhum registrado'}</dd></div>
          <div><dt>Próximo retorno</dt><dd>{selected.next_contact_on?displayDate(selected.next_contact_on):'Sem retorno agendado'}</dd></div></dl>
        {selected.status==='sent'&&!selected.customer&&<p>Identifique um cliente na proposta antes de registrar um contato ou agendar o retorno.</p>}
        {access.followup&&selected.actions.followup&&!pending&&(!followupOpen
          ? <button type="button" className="erp-secondary-button" disabled={blocked||dirty||rejecting} onClick={()=>setFollowupOpen(true)}>Registrar acompanhamento</button>
          : <form onSubmit={e=>{e.preventDefault();registerFollowup()}}>
            <fieldset disabled={blocked||dirty}>
              <label>Tipo de acompanhamento<select aria-label="Tipo de acompanhamento" value={followupKind} onChange={e=>setFollowupKind(e.target.value as 'contact'|'schedule')}>
                <option value="contact">Registrar contato realizado</option><option value="schedule">Só agendar retorno</option>
              </select></label>
              <label>Próximo retorno<input aria-label="Próximo retorno" type="date" required={followupKind==='schedule'} value={followupDate} onChange={e=>setFollowupDate(e.target.value)}/></label>
              <label>Observação do acompanhamento<textarea aria-label="Observação do acompanhamento" maxLength={255} value={followupNote} onChange={e=>setFollowupNote(e.target.value)}/></label>
              <p className="erp-sales-hint">{followupKind==='contact'?'Se não houver novo retorno, deixe a data em branco.':'Agendar não registra que o cliente foi contatado.'}</p>
              <div className="erp-sales-actions"><button type="submit" className="erp-action-button">Salvar acompanhamento</button>
                <button type="button" className="erp-secondary-button" onClick={resetFollowup}>Cancelar acompanhamento</button></div>
            </fieldset>
          </form>)}
      </section>}
      <div className="erp-card"><h2>Cliente e validade</h2><div className="erp-quote-header-fields"><label>Cliente<select aria-label="Cliente do orçamento" value={customerId} disabled={blocked || readOnly || catalogLoading} onChange={event=>{setCustomerId(event.target.value);setDirty(true)}}><option value="">Sem identificação</option>{customerId && !customers.some(item=>String(item.id)===customerId) && <option value={customerId}>{selected?.customer_name || 'Cliente indisponível'}</option>}{customers.map(customer=><option key={customer.id} value={customer.id}>{customer.name}</option>)}</select></label><label>Válido até<input aria-label="Validade do orçamento" type="date" value={validity} disabled={blocked || readOnly} onChange={event=>{setValidity(event.target.value);setDirty(true)}} /></label></div><label>Observações<textarea aria-label="Observações do orçamento" value={notes} maxLength={10000} disabled={blocked || readOnly} onChange={event=>{setNotes(event.target.value);setDirty(true)}} /></label></div>
      <div className="erp-card"><h2>Produtos da proposta</h2>{!readOnly && <div className="erp-quote-product-picker"><label>Produto<select aria-label="Produto do orçamento" value={productId} disabled={blocked || catalogLoading} onChange={event=>setProductId(event.target.value)}><option value="">Selecione</option>{products.map(product=><option key={product.id} value={product.id}>{product.internal_code} · {product.name}</option>)}</select></label><button className="erp-action-button" disabled={blocked || !productId || lines.length>=200} onClick={addProduct}>Adicionar produto</button></div>}{!lines.length && <p>Nenhum produto incluído.</p>}{lines.map((line,index)=><div className="erp-checkout-line" key={line.productId}><div className="erp-checkout-line-name"><strong>{line.name}</strong><small>{line.code}</small></div><div className="erp-checkout-line-fields"><label>Quantidade<input aria-label={`Quantidade do orçamento ${index+1}`} inputMode="decimal" value={line.quantity} disabled={blocked || readOnly} onChange={event=>changeLine(index,'quantity',event.target.value)} /></label><label>Preço (R$)<input aria-label={`Preço do orçamento ${index+1}`} inputMode="decimal" value={line.price} disabled={blocked || readOnly} onChange={event=>changeLine(index,'price',event.target.value)} /></label><label>Desconto (R$)<input aria-label={`Desconto do item ${index+1}`} inputMode="decimal" value={line.discount} disabled={blocked || readOnly} onChange={event=>changeLine(index,'discount',event.target.value)} /></label><strong>{brl(itemValues[index].total)}</strong>{!readOnly && <button className="erp-table-button is-danger" disabled={blocked} onClick={()=>{setLines(items=>items.filter((_,number)=>number!==index));setDirty(true)}}>Remover</button>}</div></div>)}</div>
      {!!selected?.events.length && <div className="erp-card"><h2>Histórico</h2><ol className="erp-sales-history">{selected.events.map(event=><li key={event.id}><strong>{events[event.action] || event.action}</strong><span>{dateTime.format(new Date(event.created_at))} · {event.creator_username}</span>{event.action==='reject'&&<p>Categoria: {lossLabels[event.loss_category]}</p>}{event.reason && <p>{event.reason}</p>}{event.next_contact_on&&<p>Retorno agendado: {displayDate(event.next_contact_on)}</p>}</li>)}</ol></div>}</div>
      <aside className="erp-card erp-checkout-summary"><span className="erp-kicker">RESUMO DA PROPOSTA</span><h2>{selected?.status_label || 'Rascunho'}</h2>{selected?.status==='rejected'&&<p>Motivo da perda: <strong>{lossLabels[selected.loss_category]}</strong></p>}<label>Desconto geral (R$)<input aria-label="Desconto geral do orçamento" inputMode="decimal" value={discount} disabled={blocked || readOnly} onChange={event=>{setDiscount(event.target.value);setDirty(true)}} /></label><div className="erp-checkout-grand-total"><span>Total</span><strong>{valid || readOnly ? brl(total) : 'Revisar valores'}</strong></div><p className="erp-sales-hint">Validade: {displayDate(validity)}. O orçamento não autoriza descontos acima do limite do perfil; essa autorização será conferida na venda.</p>{expired && !readOnly && <p className="erp-alert">Validade vencida. Revise a data antes de confirmar a proposta.</p>}{mayWrite && !closed && <>{dirty && selected && <p className="erp-sales-hint">Salvar uma revisão retorna a proposta ao rascunho e exige novo aceite.</p>}</>}{selected && dirty && <p className="erp-sales-hint">Salve as alterações antes de imprimir a proposta.</p>}{access?.reject && selected?.actions?.reject && <button className="erp-secondary-button" disabled={blocked || followupOpen || dirty} onClick={()=>{if(rejecting){setLossCategory('');setReason('')}setRejecting(!rejecting)}}>{rejecting?'Cancelar registro da perda':'Registrar perda'}</button>}{access?.reject && selected?.actions?.reject && rejecting && <fieldset className="erp-quote-loss-form" disabled={blocked||followupOpen||dirty}>
        <legend>Motivo da perda</legend>
        <p className="erp-sales-hint">Confirmar encerra a proposta e remove o retorno pendente.</p>
        <label>Categoria da perda<select aria-label="Categoria da perda" required value={lossCategory} onChange={event=>setLossCategory(event.target.value as QuoteLossCategory|'')}>
          <option value="">Selecione</option>{lossCategories.map(key=><option key={key} value={key}>{lossLabels[key]}</option>)}
        </select></label>
        <label>{lossCategory==='other'?'Descreva o motivo':'Observação (opcional)'}<textarea aria-label="Observação sobre a perda" required={lossCategory==='other'} value={reason} maxLength={255} onChange={event=>setReason(event.target.value)}/></label>
        <button className="erp-action-button" disabled={!lossCategory||(lossCategory==='other'&&!reason.trim())} onClick={()=>transition('reject')}>Confirmar perda</button>
      </fieldset>}{selected?.sale && rights.access?.can_open_sale && <><p className="erp-sales-hint">Venda #{selected.sale} criada. A proposta fica preservada; pagamento e conclusão são feitos na venda.</p><button className="erp-action-button" disabled={blocked} onClick={()=>onOpenSale(selected.sale!)}>Abrir venda {selected.sale}</button></>}{selected && dirty && <p className="erp-sales-hint">Salve as alterações antes de imprimir a proposta.</p>}{access?.print && selected?.actions?.print && <button className="erp-secondary-button" disabled={blocked || dirty} onClick={()=>{window.open(`/api/me/quotes/${selected.id}/print/?store_id=${store.id}`,'_blank','noopener,noreferrer')}}>Imprimir / Salvar PDF</button>}{access?.view && selected && <button className="erp-secondary-button" disabled={blocked} onClick={()=>void open(selected.id)}>Reabrir dados atuais</button>}{error && <p className="erp-alert" role="alert">{error}</p>}</aside>
    </div></FormDialog>}
  </section>
}
