import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError, getTransferOptions, getTransfers, submitTransfer } from '../api'
import type { AccessibleStore, StockTransfer, TransferActions, TransferAttempt, TransferPage, TransferProduct, TransferUnit } from '../api'
import FormDialog from './FormDialog'
import { dateTime, failure } from './saleMoney'
import './OperationsWindows.css'
import './StockTransfers.css'

type Props = {store:AccessibleStore;userId:number;permissions:TransferActions;onSavingChange:(value:boolean)=>void;onDirtyChange:(value:boolean)=>void}
type Line = {product:TransferProduct;quantity:string}
type Editor = 'dispatch' | 'receive' | 'return'
const empty:TransferPage={count:0,next:null,previous:null,results:[]}
const quantityFormat=new Intl.NumberFormat('pt-BR',{maximumFractionDigits:3})
const quantityText=(value:string)=>quantityFormat.format(Number(value))
const route=(item:StockTransfer)=>item.source.name+' → '+item.destination.name

export default function StockTransfers({store,userId,permissions,onSavingChange,onDirtyChange}:Props){
  const storageKey=`lentis.transfer.${userId}.${store.id}`
  const [pending,setPending]=useState<TransferAttempt|null>(()=>{try{return JSON.parse(sessionStorage.getItem(storageKey)||'null') as TransferAttempt|null}catch{return null}})
  const [result,setResult]=useState(empty)
  const [page,setPage]=useState(1)
  const [direction,setDirection]=useState('all')
  const [status,setStatus]=useState('all')
  const [reload,setReload]=useState(0)
  const [loading,setLoading]=useState(true)
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const [formError,setFormError]=useState('')
  const [notice,setNotice]=useState('')
  const [selected,setSelected]=useState<StockTransfer|null>(null)
  const [editor,setEditor]=useState<Editor|null>(null)
  const [destinations,setDestinations]=useState<TransferUnit[]>([])
  const [destination,setDestination]=useState('')
  const [products,setProducts]=useState<TransferProduct[]>([])
  const [productId,setProductId]=useState('')
  const [lines,setLines]=useState<Line[]>([])
  const [note,setNote]=useState('')
  const [confirmed,setConfirmed]=useState(false)
  const [loadingOptions,setLoadingOptions]=useState(false)
  const [optionsError,setOptionsError]=useState('')
  const locked=busy||!!pending
  const dirty=!!pending||!!editor&&(!!destination||!!lines.length||!!note||confirmed)

  useEffect(()=>{onSavingChange(busy);return()=>onSavingChange(false)},[busy,onSavingChange])
  useEffect(()=>{
    onDirtyChange(dirty)
    const warn=(event:BeforeUnloadEvent)=>{if(dirty)event.preventDefault()}
    window.addEventListener('beforeunload',warn)
    return()=>{onDirtyChange(false);window.removeEventListener('beforeunload',warn)}
  },[dirty,onDirtyChange])
  useEffect(()=>{
    let ignore=false
    setLoading(true);setError('')
    void getTransfers(store.id,page,direction,status).then(data=>{if(!ignore)setResult(data)})
      .catch(err=>{if(!ignore){setError(failure(err));setResult(empty)}})
      .finally(()=>{if(!ignore)setLoading(false)})
    return()=>{ignore=true}
  },[store.id,page,direction,status,reload])
  useEffect(()=>{
    if(editor!=='dispatch')return
    let ignore=false
    setLoadingOptions(true);setOptionsError('')
    void getTransferOptions(store.id,destination).then(data=>{
      if(!ignore){if(destination)setProducts(data.products);else setDestinations(data.destinations)}
    }).catch(err=>{if(!ignore)setOptionsError(failure(err))})
      .finally(()=>{if(!ignore)setLoadingOptions(false)})
    return()=>{ignore=true}
  },[store.id,editor,destination,reload])

  function resetEditor(next:Editor|null){
    setEditor(next);setDestination('');setProducts([]);setDestinations([]);setOptionsError('');setProductId('')
    setLines([]);setNote('');setConfirmed(false);setFormError('')
  }
  function updatePending(attempt:TransferAttempt|null){
    setPending(attempt)
    try{if(attempt)sessionStorage.setItem(storageKey,JSON.stringify(attempt));else sessionStorage.removeItem(storageKey)}catch{/* Conserva o envio em memória. */}
  }
  async function send(attempt:TransferAttempt){
    if(busy)return
    updatePending(attempt);setBusy(true);setFormError('');setNotice('')
    try{
      const saved=await submitTransfer(store.id,attempt)
      updatePending(null);resetEditor(null);setSelected(saved);setPage(1);setReload(v=>v+1)
      setNotice(`Transferência #${saved.id}: ${saved.status_label.toLowerCase()}.`)
    }catch(err){
      setFormError(failure(err))
      if(err instanceof ApiError&&err.status>=400&&err.status<500){
        updatePending(null)
        setReload(v=>v+1)
      }
    }finally{setBusy(false)}
  }
  function submit(event:FormEvent){
    event.preventDefault()
    if(locked||!confirmed)return
    const request_id=crypto.randomUUID()
    if(editor==='dispatch'){
      if(loadingOptions||optionsError||!destination||!lines.length)return
      const items=lines.map(({product,quantity})=>({source_product_id:product.source_product_id,
        destination_product_id:product.destination_product_id,quantity:quantity.trim().replace(',','.')}))
      if(items.some((item,index)=>!/^\d+(?:\.\d{1,3})?$/.test(item.quantity)||Number(item.quantity)<=0||
          Number(item.quantity)>Number(lines[index].product.source_stock))){
        setFormError('Informe quantidades positivas, com até três casas decimais, dentro do saldo de origem.')
        return
      }
      void send({id:null,payload:{request_id,destination_id:Number(destination),note:note.trim(),items}})
    }else if(selected&&editor&& (editor!=='return'||note.trim())){
      void send({id:selected.id,payload:{request_id,action:editor,note:note.trim()}})
    }
  }
  const available=products.filter(p=>!lines.some(line=>line.product.source_product_id===p.source_product_id))
  const title=editor==='dispatch'?'Nova transferência':editor==='receive'?'Confirmar recebimento':editor==='return'?'Confirmar devolução à origem':selected?`Transferência #${selected.id}`:'Conferir envio pendente'

  return <section className="erp-transfers">
    <header className="erp-page-heading erp-list-heading">
      <div><span className="erp-kicker">OPERAÇÃO · ESTOQUE</span><h1>Transferências de estoque</h1><p>Envios e recebimentos de {store.name}.</p></div>
      {permissions.add&&<button className="erp-action-button" type="button" disabled={locked} onClick={()=>{setSelected(null);setNotice('');resetEditor('dispatch')}}>Nova transferência</button>}
    </header>
    {notice&&<p className="erp-stock-success" role="status">{notice}</p>}
    <div className="erp-card erp-transfer-card" aria-busy={loading}>
      <div className="erp-transfer-filters">
        <label>Direção<select value={direction} disabled={locked} onChange={e=>{setDirection(e.target.value);setPage(1)}}>
          <option value="all">Todas</option><option value="incoming">Recebimentos</option><option value="outgoing">Envios</option>
        </select></label>
        <label>Situação<select value={status} disabled={locked} onChange={e=>{setStatus(e.target.value);setPage(1)}}>
          <option value="all">Todas</option><option value="in_transit">Em trânsito</option><option value="received">Recebida</option><option value="returned">Devolvida à origem</option>
        </select></label>
        <button type="button" className="erp-secondary-button" disabled={locked||loading} onClick={()=>setReload(v=>v+1)}>Atualizar lista</button>
      </div>
      {error?<p role="alert" className="erp-alert">{error}</p>:loading?<p role="status">Carregando transferências…</p>:!result.results.length?<p>Nenhuma transferência neste filtro.</p>:
        <ul className="erp-transfer-list">{result.results.map(item=><li key={item.id}>
          <button type="button" className="erp-secondary-button" disabled={locked} onClick={()=>{setSelected(item);setNotice('');resetEditor(null)}}>
            <span><strong>#{item.id} · {route(item)}</strong><small>{item.items.length} {item.items.length===1?'item':'itens'} · {dateTime.format(new Date(item.sent_at))}</small></span>
            <span className={`erp-transfer-badge is-${item.status}`}>{item.status_label}</span>
          </button>
        </li>)}</ul>}
      <div className="erp-transfer-filters"><button type="button" className="erp-secondary-button" disabled={locked||loading||page===1} onClick={()=>setPage(v=>v-1)}>Anterior</button>
        <span>Página {page}</span><button type="button" className="erp-secondary-button" disabled={locked||loading||!result.next} onClick={()=>setPage(v=>v+1)}>Próxima</button></div>
    </div>

    {(editor||selected||pending)&&<FormDialog title={title} sectionLabel="OPERAÇÃO · TRANSFERÊNCIAS" subtitle={selected?route(selected):store.name}
      busy={busy} dirty={dirty} notice={formError} onClose={()=>{setSelected(null);resetEditor(null)}}
      actions={pending? <button type="button" className="erp-action-button" disabled={busy} onClick={()=>void send(pending)}>Conferir / repetir envio</button>
        :editor?<button type="submit" form="lentis-transfer-form" className="erp-action-button" disabled={busy||!confirmed||
          (editor==='dispatch'&&(!lines.length||loadingOptions||!!optionsError))||(editor==='return'&&!note.trim())}>
          {editor==='dispatch'?'Registrar envio':editor==='receive'?'Registrar recebimento':'Registrar devolução'}
        </button>:selected&&<>
          {selected.can_receive&&<button type="button" className="erp-action-button" onClick={()=>resetEditor('receive')}>Confirmar recebimento</button>}
          {selected.can_return&&<button type="button" className="erp-secondary-button" onClick={()=>resetEditor('return')}>Confirmar devolução à origem</button>}
        </>}>
      {formError&&<p className="erp-alert" role="alert">{formError}</p>}
      {pending?<p>Repita o mesmo envio para conferir o resultado sem duplicar a movimentação.</p>:<>
        {selected&&<div className="erp-transfer-detail">
          <p><strong>{selected.status_label}</strong> · Enviada por {selected.sent_by} em {dateTime.format(new Date(selected.sent_at))}.</p>
          {selected.note&&<p>Observação: {selected.note}</p>}
          {selected.resolved_at&&<p>Encerrada por {selected.resolved_by} em {dateTime.format(new Date(selected.resolved_at))}{selected.resolution_note&&` · ${selected.resolution_note}`}.</p>}
          <ul>{selected.items.map(item=><li key={item.id}><strong>{quantityText(item.quantity)} · {item.source_label}</strong>
            {item.destination_label!==item.source_label&&<small>No destino: {item.destination_label}</small>}
            <small>Movimento de saída #{item.outgoing_movement_id}{item.incoming_movement_id!==null&&` · Movimento de entrada #${item.incoming_movement_id}`}</small></li>)}</ul>
        </div>}
        {editor&&<form id="lentis-transfer-form" className="erp-customer-form erp-transfer-form" onSubmit={submit}>
          {editor==='dispatch'&&<>
            <p>Origem: <strong>{store.name}</strong>. O envio baixa o saldo desta unidade. A entrada só é registrada no destino após a conferência.</p>
            <label>Unidade de destino<select value={destination} required disabled={loadingOptions&&!destination} onChange={e=>{
              if(lines.length&&!window.confirm('Trocar o destino remove os itens selecionados. Continuar?'))return
              setDestination(e.target.value);setProducts([]);setProductId('');setLines([]);setConfirmed(false)
            }}><option value="">Selecione a unidade</option>{destinations.map(unit=><option key={unit.id} value={unit.id}>{unit.name}</option>)}</select></label>
            {loadingOptions?<p role="status">Conferindo unidades e produtos…</p>:optionsError?<p className="erp-alert" role="alert">{optionsError}</p>
              :!destinations.length?<p>Nenhuma outra unidade ativa desta empresa está disponível no seu acesso.</p>
              :destination&&!products.length?<p>Nenhum produto com saldo tem cadastro ativo correspondente no destino.</p>:null}
            {destination&&products.length>0&&<div className="erp-transfer-filters">
              <label>Produto<select value={productId} onChange={e=>setProductId(e.target.value)}>
                <option value="">Selecione o produto</option>{available.map(product=><option key={product.source_product_id} value={product.source_product_id}>{product.source_label} · saldo {quantityText(product.source_stock)}</option>)}
              </select></label>
              <button type="button" className="erp-secondary-button" disabled={!productId||lines.length>=30} onClick={()=>{
                const product=available.find(p=>String(p.source_product_id)===productId)
                if(product){setLines(current=>[...current,{product,quantity:'1'}]);setProductId('');setConfirmed(false)}
              }}>Adicionar produto</button>
            </div>}
            {lines.map(({product,quantity},index)=><div key={product.source_product_id} className="erp-transfer-line">
              <div><strong>{product.source_label}</strong><small>No destino: {product.destination_label} · saldo na origem: {quantityText(product.source_stock)}</small></div>
              <label>Quantidade de {product.source_label}<input required inputMode="decimal" value={quantity} pattern="[0-9]+([.,][0-9]{1,3})?" onChange={e=>{
                setLines(current=>current.map((line,i)=>i===index?{...line,quantity:e.target.value}:line));setConfirmed(false)
              }}/></label>
              <button type="button" className="erp-secondary-button" aria-label={`Remover ${product.source_label}`} onClick={()=>{setLines(current=>current.filter((_,i)=>i!==index));setConfirmed(false)}}>Remover</button>
            </div>)}
          </>}
          {editor==='receive'&&<p>Confirme depois de conferir todos os itens físicos. O registro acrescenta o saldo nesta unidade.</p>}
          {editor==='return'&&<p>Confirme somente se todos os itens retornaram fisicamente à origem. O saldo será reposto nesta unidade.</p>}
          <label>{editor==='return'?'Motivo da devolução':'Observação (opcional)'}<textarea value={note} maxLength={255} required={editor==='return'} onChange={e=>setNote(e.target.value)}/></label>
          <label className="erp-transfer-confirm"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>
            {editor==='dispatch'?'Confirmo o envio dos itens listados.':editor==='receive'?'Conferi e recebi todos os itens.':'Conferi que todos os itens voltaram à origem.'}
          </label>
        </form>}
      </>}
    </FormDialog>}
  </section>
}
