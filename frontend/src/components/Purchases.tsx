import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError, getMyProducts, getSuppliers, getPurchases, getPurchase, submitPurchase } from '../api'
import type { AccessibleStore, Product, Supplier, Purchase, PurchaseAttempt, PurchasesPage } from '../api'
import { decimal, decimalText, dateTime, today, failure } from './saleMoney'
import './Purchases.css'

type Props={store:AccessibleStore;userId:number;onSavingChange:(v:boolean)=>void;onDirtyChange:(v:boolean)=>void;onPayables?:(id:number)=>void}
type Line={productId:number;name:string;code:string;quantity:string;cost:string}
function currency(value:string|bigint){const cents=typeof value==='bigint'?value:decimal(value);return cents===null?'—':`R$ ${new Intl.NumberFormat('pt-BR',{maximumFractionDigits:0}).format(cents/100n)},${(cents%100n).toString().padStart(2,'0')}`}
const empty:PurchasesPage={count:0,next:null,previous:null,results:[],can_create:false,can_receive:false}
function totalLine(line:Line){const q=decimal(line.quantity,3),c=decimal(line.cost);return q!==null&&c!==null?(q*c+500n)/1000n:null}

export default function Purchases({store,userId,onSavingChange,onDirtyChange,onPayables}:Props){
  const storageKey=`lentis.purchase.${userId}.${store.id}`
  const [pending,setPending]=useState<PurchaseAttempt|null>(()=>{try{return JSON.parse(sessionStorage.getItem(storageKey)||'null') as PurchaseAttempt|null}catch{return null}})
  const [result,setResult]=useState(empty)
  const [page,setPage]=useState(1)
  const [status,setStatus]=useState('all')
  const [reload,setReload]=useState(0)
  const [selected,setSelected]=useState<Purchase|null>(null)
  const [editor,setEditor]=useState(false)
  const [suppliers,setSuppliers]=useState<Supplier[]>([])
  const [supplierPage,setSupplierPage]=useState(1)
  const [supplierNext,setSupplierNext]=useState(false)
  const [products,setProducts]=useState<Product[]>([])
  const [catalogError,setCatalogError]=useState('')
  const [catalogLoading,setCatalogLoading]=useState(true)
  const [supplierId,setSupplierId]=useState('')
  const [reference,setReference]=useState('')
  const [documentDate,setDocumentDate]=useState(today())
  const [notes,setNotes]=useState('')
  const [lines,setLines]=useState<Line[]>([])
  const [productId,setProductId]=useState('')
  const [reason,setReason]=useState('')
  const [updateCost,setUpdateCost]=useState(false)
  const [confirmed,setConfirmed]=useState(false)
  const [review,setReview]=useState(false)
  const [dirty,setDirty]=useState(false)
  const [busy,setBusy]=useState(false)
  const [loading,setLoading]=useState(true)
  const [error,setError]=useState('')
  const [success,setSuccess]=useState('')
  const locked=busy||!!pending
  const readOnly=!!selected&&!selected.can_edit
  const total=lines.reduce((sum,line)=>sum+(totalLine(line)??0n),0n)
  useEffect(()=>{onSavingChange(busy);return()=>onSavingChange(false)},[busy,onSavingChange])
  useEffect(()=>{onDirtyChange(dirty||!!reason||!!pending||review);return()=>onDirtyChange(false)},[dirty,reason,pending,review,onDirtyChange])
  useEffect(()=>{const warn=(e:BeforeUnloadEvent)=>{if(dirty||reason||pending||review)e.preventDefault()};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn)},[dirty,reason,pending,review])
  useEffect(()=>{let ignore=false;setLoading(true);setError('');void getPurchases(store.id,page,status).then(v=>{if(!ignore)setResult(v)}).catch(e=>{if(!ignore){setResult(empty);setError(failure(e));setEditor(false);setSelected(null)}}).finally(()=>{if(!ignore)setLoading(false)});return()=>{ignore=true}},[store.id,page,status,reload])
  useEffect(()=>{let ignore=false;setCatalogError('');setCatalogLoading(true);void Promise.all([getSuppliers(store.id,supplierPage,'active'),getMyProducts(store.id)]).then(([s,p])=>{if(!ignore){setSuppliers(s.results);setSupplierNext(!!s.next);setProducts(p)}}).catch(e=>{if(!ignore){setCatalogError(failure(e));setSuppliers([]);setProducts([])}}).finally(()=>{if(!ignore)setCatalogLoading(false)});return()=>{ignore=true}},[store.id,supplierPage,reload])
  function accept(p:Purchase){setSelected(p);setEditor(true);setSupplierId(String(p.supplier_id));setReference(p.reference);setDocumentDate(p.document_date||'');setNotes(p.notes);setLines((p.items||[]).map(i=>({productId:i.product_id,name:i.product_name,code:i.product_code,quantity:i.quantity.replace('.',','),cost:i.unit_cost.replace('.',',')})));setReason('');setDirty(false);setReview(false);setConfirmed(false);setUpdateCost(false)}
  function allowed(){return !dirty&&!reason||window.confirm('Descartar alterações não salvas da compra?')}
  async function open(id:number){if(locked||!allowed())return;setBusy(true);setError('');try{accept(await getPurchase(store.id,id))}catch(e){setError(failure(e));setSelected(null);setEditor(false)}finally{setBusy(false)}}
  function newPurchase(){if(locked||!allowed())return;setSelected(null);setEditor(true);setSupplierId('');setReference('');setDocumentDate(today());setNotes('');setLines([]);setReason('');setDirty(false);setError('');setSuccess('');setUpdateCost(false);setReview(false)}
  function addProduct(){const p=products.find(p=>String(p.id)===productId);if(!p)return;if(lines.some(l=>l.productId===p.id)){setError('O produto já está na compra. Ajuste a quantidade da linha.');return}setLines([...lines,{productId:p.id,name:p.name,code:p.internal_code,quantity:'1',cost:p.cost_price.replace('.',',')}]);setProductId('');setDirty(true);setError('')}
  function changeLine(index:number,key:'quantity'|'cost',value:string){setLines(lines.map((l,i)=>i===index?{...l,[key]:value}:l));setDirty(true)}
  function draftAttempt():PurchaseAttempt|null{
    if(!supplierId||!lines.length){setError('Selecione o fornecedor e adicione ao menos um produto.');return null}
    const items=[]
    for(const l of lines){const q=decimal(l.quantity,3),c=decimal(l.cost);if(q===null||q<=0n||c===null){setError('Informe quantidade positiva com até 3 casas e custo não negativo com até 2 casas.');return null}items.push({product_id:l.productId,quantity:decimalText(q,3),unit_cost:decimalText(c)})}
    return {id:selected?.id??null,payload:{request_id:crypto.randomUUID(),action:selected?'update':'create',...(selected?{expected_version:selected.version}:{}),supplier_id:Number(supplierId),reference,document_date:documentDate||null,notes,items}}
  }
  async function send(attempt:PurchaseAttempt):Promise<Purchase|null>{
    if(busy)return null;setBusy(true);setPending(attempt);setError('');setSuccess('');setReview(false)
    try{sessionStorage.setItem(storageKey,JSON.stringify(attempt))}catch{/* Identificador também mantido em memória. */}
    try{const p=await submitPurchase(store.id,attempt);setPending(null);try{sessionStorage.removeItem(storageKey)}catch{/* Sem armazenamento disponível. */}accept(p);setReload(v=>v+1);setSuccess(p.status==='received'?'Entrada confirmada. Estoque e histórico registrados.':p.status==='cancelled'?'Rascunho cancelado.':'Rascunho salvo. A entrada de estoque ainda não foi realizada.');return p}
    catch(e){setError(failure(e));if(e instanceof ApiError&&e.status>=400&&e.status<500){setPending(null);try{sessionStorage.removeItem(storageKey)}catch{/* Sem armazenamento disponível. */}}return null}
    finally{setBusy(false)}
  }
  function save(e:FormEvent){e.preventDefault();if(locked)return;const attempt=draftAttempt();if(attempt)void send(attempt)}
  async function prepare(){if(locked)return;let current=selected;if(!current||dirty){const attempt=draftAttempt();if(!attempt)return;current=await send(attempt)}if(current?.can_receive){setReview(true);setConfirmed(false)}}
  function receive(){if(!selected||locked||!confirmed)return;void send({id:selected.id,payload:{request_id:crypto.randomUUID(),action:'receive',expected_version:selected.version,confirmed:true,update_cost:updateCost}})}
  function cancel(){if(!selected||locked)return;if(dirty){setError('Salve as alterações ou reabra a compra antes de cancelar.');return}if(!reason.trim()){setError('Informe o motivo para cancelar o rascunho.');return}if(window.confirm('Cancelar este rascunho de compra?'))void send({id:selected.id,payload:{request_id:crypto.randomUUID(),action:'cancel',expected_version:selected.version,reason}})}
  return <section className="purchase-page">
    <header className="purchase-heading"><div><span className="erp-kicker">COMERCIAL · {store.name}</span><h1>Compras e entradas</h1><p>Registre a compra, confira os itens e confirme a entrada no estoque.</p></div><button className="erp-action-button" type="button" disabled={locked||!result.can_create} onClick={newPurchase}>Nova compra</button></header>
    {error&&<p className="erp-alert" role="alert">{error}</p>}{success&&<p className="purchase-success" role="status">{success}</p>}
    {pending&&<div className="erp-card"><h2>Conferir envio pendente</h2><p>Repita o mesmo envio para recuperar o resultado sem duplicar compra ou entrada de estoque.</p><button type="button" className="erp-action-button" disabled={busy} onClick={()=>void send(pending)}>Conferir / repetir envio</button></div>}
    <div className="purchase-toolbar"><label>Situação<select aria-label="Situação das compras" value={status} disabled={locked} onChange={e=>{setStatus(e.target.value);setPage(1)}}><option value="all">Todas</option><option value="draft">Rascunhos</option><option value="received">Entradas confirmadas</option><option value="cancelled">Canceladas</option></select></label><button type="button" disabled={locked} onClick={()=>setReload(v=>v+1)}>Atualizar lista</button></div>
    <div className="purchase-grid"><div className="erp-card"><h2>Compras <small>({result.count})</small></h2>{loading?<p role="status">Carregando…</p>:!result.results.length?<p>Nenhuma compra neste filtro.</p>:result.results.map(p=><button type="button" key={p.id} className={`purchase-row${selected?.id===p.id?' is-selected':''}`} disabled={locked} onClick={()=>void open(p.id)}><strong>#{p.id} · {p.supplier_name}</strong><span>{p.status_label} · {currency(p.total)}</span><small>{p.reference||'Sem referência'} · {dateTime.format(new Date(p.created_at))}</small></button>)}<div className="purchase-pagination"><button type="button" disabled={locked||!result.previous} onClick={()=>setPage(v=>v-1)}>Anterior</button><span>Página {page}</span><button type="button" disabled={locked||!result.next} onClick={()=>setPage(v=>v+1)}>Próxima</button></div></div>
    <div className="erp-card purchase-detail">{!editor?<><h2>Entrada de mercadorias</h2><p>Abra uma compra ou crie um rascunho para iniciar a conferência.</p></>:<><h2>{selected?`Compra #${selected.id} · ${selected.status_label}`:'Nova compra'}</h2>{selected&&<p className="purchase-hint">Versão {selected.version}{selected.received_at?` · Entrada em ${dateTime.format(new Date(selected.received_at))}`:''}</p>}
    {catalogError&&!readOnly&&<p className="erp-alert">Catálogo indisponível: {catalogError}. Confira as permissões e use Atualizar lista.</p>}
    <form onSubmit={save}><fieldset disabled={locked||readOnly||catalogLoading||!!catalogError}><legend>Fornecedor e documento</legend>{selected?.status==='received'?<div className="purchase-supplier-copy"><strong>{selected.supplier_name}</strong><p>{selected.supplier_snapshot?.document||'Documento não informado'}</p><p>{[selected.supplier_snapshot?.street,selected.supplier_snapshot?.address_number,selected.supplier_snapshot?.city,selected.supplier_snapshot?.state].filter(Boolean).join(' · ')}</p></div>:<><label>Fornecedor<select aria-label="Fornecedor da compra" required value={supplierId} onChange={e=>{setSupplierId(e.target.value);setDirty(true)}}><option value="">Selecione</option>{supplierId&&!suppliers.some(s=>String(s.id)===supplierId)&&<option value={supplierId}>{selected?.supplier_name||`Fornecedor #${supplierId}`}</option>}{suppliers.map(s=><option key={s.id} value={s.id}>{s.name}{s.document?` · ${s.document}`:''}</option>)}</select></label><div className="purchase-pagination"><button type="button" disabled={supplierPage===1} onClick={()=>setSupplierPage(v=>v-1)}>Fornecedores anteriores</button><button type="button" disabled={!supplierNext} onClick={()=>setSupplierPage(v=>v+1)}>Mais fornecedores</button></div></>}<div className="purchase-fields"><label>Referência do documento<input maxLength={60} value={reference} onChange={e=>{setReference(e.target.value);setDirty(true)}} placeholder="Número ou referência interna"/></label><label>Data do documento<input type="date" value={documentDate} onChange={e=>{setDocumentDate(e.target.value);setDirty(true)}}/></label></div><label>Observações<textarea maxLength={4000} value={notes} onChange={e=>{setNotes(e.target.value);setDirty(true)}}/></label></fieldset>
    <fieldset disabled={locked||readOnly||catalogLoading||!!catalogError}><legend>Itens da compra</legend>{!readOnly&&<div className="purchase-add"><label>Produto<select aria-label="Produto da compra" value={productId} onChange={e=>setProductId(e.target.value)}><option value="">Selecione um produto</option>{products.map(p=><option key={p.id} value={p.id}>{p.internal_code} · {p.name}</option>)}</select></label><button type="button" onClick={addProduct} disabled={!productId||lines.length>=100}>Adicionar produto</button></div>}<div className="purchase-lines">{lines.map((l,i)=><article key={l.productId}><strong>{l.code} · {l.name}</strong><div className="purchase-line-fields"><label>Quantidade<input aria-label={`Quantidade do item ${i+1}`} inputMode="decimal" value={l.quantity} onChange={e=>changeLine(i,'quantity',e.target.value)}/></label><label>Custo unitário<input aria-label={`Custo do item ${i+1}`} inputMode="decimal" value={l.cost} onChange={e=>changeLine(i,'cost',e.target.value)}/></label><strong>{totalLine(l)===null?'Valor inválido':currency(totalLine(l)!)}</strong>{!readOnly&&<button type="button" onClick={()=>{setLines(lines.filter((_,n)=>n!==i));setDirty(true)}}>Remover</button>}</div>{selected?.status==='received'&&<small>Movimentação #{selected.items?.find(x=>x.product_id===l.productId)?.movement_id}</small>}</article>)}</div><strong className="purchase-total">Total dos itens: {currency(total)}</strong>{!readOnly&&<button className="erp-action-button" type="submit">Salvar rascunho</button>}</fieldset></form>
    {!readOnly&&<button type="button" className="erp-action-button" disabled={locked||catalogLoading||!!catalogError||(!selected&&!result.can_receive)||!!selected&&!selected.can_receive} onClick={()=>void prepare()}>Conferir entrada</button>}
    {selected?.status==='received'&&<p className="purchase-hint">{selected.updates_cost?'O custo cadastrado dos produtos foi atualizado pelo custo desta entrada.':'O custo cadastrado dos produtos foi preservado.'} Compra confirmada é somente leitura.</p>}
    {selected?.status==='received'&&(decimal(selected.total)??0n)>0n&&onPayables&&<button type="button" className="erp-action-button" disabled={locked} onClick={()=>onPayables(selected.id)}>Gerar / consultar contas a pagar</button>}
    {selected?.can_edit&&<fieldset disabled={locked}><legend>Cancelar rascunho</legend><label>Motivo do cancelamento<textarea maxLength={255} value={reason} onChange={e=>setReason(e.target.value)}/></label><button type="button" onClick={cancel}>Cancelar rascunho</button></fieldset>}
    {selected&&<><h3>Histórico de operações</h3><div className="purchase-history">{selected.events?.map(e=><article key={e.version}><strong>{e.action_label} · versão {e.version}</strong><small>{dateTime.format(new Date(e.created_at))} · {e.creator_username}</small>{e.reason&&<p>{e.reason}</p>}</article>)}</div><button type="button" disabled={locked} onClick={()=>void open(selected.id)}>Reabrir dados atuais</button></>}
    </>}</div></div>
    {review&&selected&&<div className="purchase-overlay"><section className="erp-card purchase-review" role="dialog" aria-modal="true" aria-labelledby="purchase-review-title"><h2 id="purchase-review-title">Conferir entrada da compra #{selected.id}</h2><p>{selected.supplier_name} · {selected.reference||'Sem referência'}</p><ul>{selected.items?.map(i=><li key={i.id}>{i.product_code} · {i.product_name} — {i.quantity.replace('.',',')} × {currency(i.unit_cost)}</li>)}</ul><strong>Total: {currency(selected.total)}</strong><label className="purchase-check"><input type="checkbox" checked={updateCost} onChange={e=>setUpdateCost(e.target.checked)}/>Atualizar custo cadastrado pelo custo desta entrada</label><p className="purchase-hint">Esta opção usa o último custo informado, sem cálculo de custo médio. O preço de venda não será alterado.</p><label className="purchase-check"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>Conferi os produtos, quantidades e custos e autorizo a entrada</label><div className="purchase-toolbar"><button type="button" disabled={busy} onClick={()=>setReview(false)}>Voltar à compra</button><button type="button" className="erp-action-button" disabled={busy||!confirmed} onClick={receive}>Confirmar entrada</button></div></section></div>}
  </section>
}
