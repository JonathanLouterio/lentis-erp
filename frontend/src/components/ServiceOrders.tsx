import { useClinicalAccess } from '../hooks/useClinicalAccess'
import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError, getOrderSales, getServiceOrder, getServiceOrders, submitServiceOrder } from '../api'
import type { AccessibleStore, ServiceOrder, ServiceOrderAttempt, ServiceOrderPage } from '../api'
import { dateTime, failure, today } from './saleMoney'
import './ServiceOrders.css'
import FormDialog from './FormDialog'
import './OperationsWindows.css'
import { useOrderAccess } from '../hooks/useOrderAccess'

type Props = {store:AccessibleStore;userId:number;initialSaleId?:number;onSavingChange:(v:boolean)=>void;onDirtyChange:(v:boolean)=>void}
const labels:Record<string,string>={open:'Aberta',laboratory:'No laboratório',mounting:'Em montagem',checking:'Em conferência',ready:'Pronta para entrega',delivered:'Entregue',cancelled:'Cancelada'}
const actions:Record<string,string>={create:'Abertura',update:'Alteração',advance:'Avanço de etapa',rework:'Retrabalho',cancel:'Cancelamento'}
const blank=()=>({promised_on:today(),laboratory:'',frame_description:'',lens_description:'',notes:''})
const empty:ServiceOrderPage={count:0,next:null,previous:null,results:[],can_create:false}

export default function ServiceOrders({store,userId,initialSaleId,onSavingChange,onDirtyChange}:Props){
  const storageKey=`lentis.os.${userId}.${store.id}`
  const [pending,setPending]=useState<ServiceOrderAttempt|null>(()=>{try{return JSON.parse(sessionStorage.getItem(storageKey)||'null') as ServiceOrderAttempt|null}catch{return null}})
  const [result,setResult]=useState(empty)
  const [page,setPage]=useState(1)
  const [status,setStatus]=useState('active')
  const [overdue,setOverdue]=useState(false)
  const [reload,setReload]=useState(0)
  const [selected,setSelected]=useState<ServiceOrder|null>(null)
  const [cancelReview,setCancelReview]=useState(false)
  const [creating,setCreating]=useState(false)
  const [saleId,setSaleId]=useState(initialSaleId?String(initialSaleId):'')
  const [sales,setSales]=useState<{id:number;customer_name:string}[]>([])
  const [salesPage,setSalesPage]=useState(1)
  const [salesNext,setSalesNext]=useState(false)
  const [form,setForm]=useState(blank)
  const [reason,setReason]=useState('')
  const [target,setTarget]=useState<'laboratory'|'mounting'>('laboratory')
  const [confirmed,setConfirmed]=useState(false)
  const [dirty,setDirty]=useState(false)
  const [busy,setBusy]=useState(false)
  const [loading,setLoading]=useState(true)
  const [error,setError]=useState('')
  const [notice,setNotice]=useState('')
  const clinicalRights=useClinicalAccess(store.id,reload)
  const rights=useOrderAccess(store.id,reload)
  const caps=rights.access?.actions
  const locked=busy||!!pending
  useEffect(()=>{onSavingChange(busy);return()=>onSavingChange(false)},[busy,onSavingChange])
  useEffect(()=>{onDirtyChange(dirty||!!pending||!!reason);return()=>onDirtyChange(false)},[dirty,pending,reason,onDirtyChange])
  useEffect(()=>{const warn=(e:BeforeUnloadEvent)=>{if(dirty||pending||reason)e.preventDefault()};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn)},[dirty,pending,reason])
  useEffect(()=>{let ignore=false;setLoading(true);void getServiceOrders(store.id,page,status,overdue).then(v=>{if(!ignore)setResult(v)}).catch(e=>{if(!ignore){setError(failure(e));setResult(empty)}}).finally(()=>{if(!ignore)setLoading(false)});return()=>{ignore=true}},[store.id,page,status,overdue,reload])
  useEffect(()=>{if(!creating||!caps?.create)return;let ignore=false;void getOrderSales(store.id,salesPage).then(v=>{if(!ignore){setSales(v.results);setSalesNext(!!v.next)}}).catch(e=>{if(!ignore)setError(failure(e))});return()=>{ignore=true}},[store.id,creating,salesPage,caps?.create])
  useEffect(()=>{if(!initialSaleId||pending||!caps?.view)return;let ignore=false;setBusy(true);void getServiceOrders(store.id,1,'all',false,initialSaleId).then(async v=>{if(ignore)return;if(v.results[0]){const order=await getServiceOrder(store.id,v.results[0].id);if(!ignore)hydrate(order)}else if(caps?.create){setCreating(true);setSaleId(String(initialSaleId))}}).catch(e=>{if(!ignore)setError(failure(e))}).finally(()=>{if(!ignore)setBusy(false)});return()=>{ignore=true}},[store.id,initialSaleId,caps?.view,caps?.create])
  function hydrate(order:ServiceOrder){setSelected(order);setCreating(false);setForm({promised_on:order.promised_on,laboratory:order.laboratory,frame_description:order.frame_description,lens_description:order.lens_description,notes:order.notes});setReason('');setConfirmed(false);setDirty(false)}
  async function open(id:number){if(locked||dirty&&!window.confirm('Descartar as alterações não salvas?'))return;setBusy(true);setError('');setNotice('');try{hydrate(await getServiceOrder(store.id,id))}catch(e){setError(failure(e))}finally{setBusy(false)}}
  async function send(attempt:ServiceOrderAttempt){if(busy||!caps?.[attempt.payload.action]){setError('Você não tem permissão para esta ação.');return}setPending(attempt);try{sessionStorage.setItem(storageKey,JSON.stringify(attempt))}catch{/* O envio permanece na memória desta tela. */}setBusy(true);setError('');setNotice('');try{const saved=await submitServiceOrder(store.id,attempt);try{sessionStorage.removeItem(storageKey)}catch{/* Sem armazenamento disponível. */}setPending(null);hydrate(saved);setReload(v=>v+1);setNotice('OS registrada. Histórico atualizado.')}catch(e){setError(failure(e));if(e instanceof ApiError&&e.status>=400&&e.status<500){try{sessionStorage.removeItem(storageKey)}catch{/* Sem armazenamento disponível. */}setPending(null)}}finally{setBusy(false)}}
  function operation(action:ServiceOrderAttempt['payload']['action']){if(locked||!selected)return;if(dirty&&action!=='update'){setError('Salve as alterações dos campos antes de mudar a etapa.');return}void send({id:selected.id,payload:{request_id:crypto.randomUUID(),action,expected_version:selected.version,reason,confirmed,target_status:target,...(action==='update'?form:{})}})}
  function save(e:FormEvent){e.preventDefault();if(locked)return;if(creating){void send({id:null,payload:{request_id:crypto.randomUUID(),action:'create',sale_id:Number(saleId),...form}})}else operation('update')}
  function closeEditor(){setSelected(null);setCreating(false);setCancelReview(false);setForm(blank());setSaleId('');setReason('');setConfirmed(false);setDirty(false);setError('');setNotice('')}
  function newOrder(){if(locked||dirty&&!window.confirm('Descartar as alterações não salvas?'))return;setSelected(null);setCreating(true);setSaleId('');setSalesPage(1);setConfirmed(false);setTarget('laboratory');setForm(blank());setReason('');setDirty(false);setError('');setNotice('')}
  const editable=creating?!!caps?.create:!!caps?.update&&!!selected?.actions.update
  if(!caps?.view)return <section className="erp-card"><h1>Ordens de serviço</h1><p>{rights.loading?'Conferindo acessos…':rights.error||'Solicite permissão para consultar ordens de serviço.'}</p></section>
  return <section className="os-page">
    <header className="os-heading"><div><span className="eyebrow">OPERAÇÃO · {store.name}</span><h1>Ordens de serviço</h1><p>Da preparação à entrega, com cada etapa registrada.</p></div><button type="button" className="primary-button" hidden={!caps.create} disabled={locked} onClick={newOrder}>Nova OS</button></header>
    {error&&<p className="error-message" role="alert">{error}</p>}{notice&&<p role="status" className="os-notice">{notice}</p>}

    <div className="os-filters"><label>Situação<select aria-label="Situação da OS" value={status} disabled={locked} onChange={e=>{setStatus(e.target.value);setPage(1)}}><option value="active">Em andamento</option><option value="all">Todas</option>{Object.entries(labels).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label><label className="os-check"><input type="checkbox" checked={overdue} disabled={locked} onChange={e=>{setOverdue(e.target.checked);setPage(1)}}/>Somente atrasadas</label><button type="button" disabled={locked} onClick={()=>setReload(v=>v+1)}>Atualizar lista</button></div>
    <div className="os-grid"><div className="erp-card os-list" aria-busy={loading}><h2>Fila de atendimento <small>({result.count})</small></h2>{loading?<p role="status">Carregando…</p>:result.results.length===0?<p>Nenhuma OS neste filtro.</p>:result.results.map(o=><button type="button" className={`os-row${selected?.id===o.id?' is-selected':''}`} disabled={locked} key={o.id} onClick={()=>void open(o.id)}><span><strong>OS #{o.id} · {o.customer_name}</strong><small>Venda #{o.sale_id} · Entrega {o.promised_on.split('-').reverse().join('/')}</small></span><span className={o.overdue?'os-late':'os-badge'}>{o.overdue?'Atrasada · ':''}{o.status_label}</span>{o.sale_status==='cancelled'&&<small className="os-late">Venda cancelada: confira e cancele a OS.</small>}</button>)}<div className="os-pagination"><button type="button" disabled={locked||page===1} onClick={()=>setPage(v=>v-1)}>Anterior</button><span>Página {page}</span><button type="button" disabled={locked||!result.next} onClick={()=>setPage(v=>v+1)}>Próxima</button></div></div>
    </div>
    {(creating || selected || pending) && <FormDialog wide
      title={creating?'Abrir ordem de serviço':selected?`OS #${selected.id} · ${selected.status_label}`:'Conferir envio pendente'}
      sectionLabel="OPERAÇÃO · ORDENS DE SERVIÇO" subtitle={store.name} busy={locked} dirty={dirty||!!reason||confirmed}
      notice={error||notice} onClose={closeEditor}
      actions={!pending && <>
        {editable && <button type="submit" form="lentis-order-form" className="erp-action-button" disabled={locked||rights.loading}>{busy?'Salvando…':creating?'Abrir OS':'Salvar dados de produção'}</button>}
        {selected&&caps.advance&&selected.actions.advance&&<button type="button" className="erp-action-button" disabled={locked||rights.loading||selected.sale_status!=='completed'} onClick={()=>operation('advance')}>Avançar: {labels[selected.next_status||'']||'—'}</button>}
      </>}>
      {error&&<p className="erp-alert" role="alert">{error}</p>}{notice&&<p className="os-notice" role="status">{notice}</p>}
      {pending&&<div className="erp-card"><strong>{busy?'Registrando operação…':'Envio pendente de confirmação'}</strong><p>Repita o mesmo envio para recuperar o resultado sem duplicar a OS ou a etapa. Os campos ficam bloqueados até a confirmação.</p><button type="button" disabled={busy||rights.loading||!caps[pending.payload.action]} onClick={()=>void send(pending)}>Conferir / repetir envio</button></div>}
      {!pending && <div className="os-detail">
      {selected&&<><p>Venda #{selected.sale_id} · {selected.customer_name} · versão {selected.version}</p><ol className="os-steps">{Object.entries(labels).filter(([k])=>k!=='cancelled').map(([k,v])=><li key={k} aria-current={selected.status===k?'step':undefined}>{v}</li>)}</ol>{selected.sale_status==='cancelled'&&<p className="error-message">A venda foi cancelada. A OS mantém o histórico; cancele a ordem para encerrar a produção.</p>}</>}
      <form id="lentis-order-form" onSubmit={save}><fieldset disabled={locked||!editable}><legend>Dados de produção</legend>
      {creating&&<><label>Venda finalizada com cliente<select aria-label="Venda finalizada com cliente" required value={saleId} onChange={e=>{setSaleId(e.target.value);setDirty(true)}}><option value="">Selecione a venda</option>{initialSaleId&&!sales.some(s=>s.id===initialSaleId)&&<option value={initialSaleId}>Venda #{initialSaleId}</option>}{sales.map(s=><option key={s.id} value={s.id}>#{s.id} · {s.customer_name}</option>)}</select></label><div className="os-pagination"><button type="button" disabled={salesPage===1} onClick={()=>setSalesPage(v=>v-1)}>Vendas anteriores</button><button type="button" disabled={!salesNext} onClick={()=>setSalesPage(v=>v+1)}>Mais vendas</button></div><p className="os-hint">Uma OS por venda. A cópia da receita será preservada, quando houver vínculo na venda.</p></>}
      <div className="os-fields">{(['promised_on','laboratory','frame_description','lens_description'] as const).map(key=><label key={key}>{({promised_on:'Previsão de entrega',laboratory:'Laboratório',frame_description:'Armação / identificação',lens_description:'Lentes / tratamento'})[key]}<input type={key==='promised_on'?'date':'text'} required={key==='promised_on'} maxLength={key==='laboratory'?180:key==='lens_description'?500:255} value={form[key]} onChange={e=>{setForm({...form,[key]:e.target.value});setDirty(true)}}/></label>)}</div><label>Observações operacionais<textarea maxLength={4000} value={form.notes} onChange={e=>{setForm({...form,notes:e.target.value});setDirty(true)}}/></label>
      </fieldset></form>      {!creating&&selected&&(editable||caps.advance&&selected.actions.advance||caps.rework&&selected.actions.rework||caps.cancel&&selected.actions.cancel)&&<label>Motivo da alteração / observação da etapa / quem recebeu<textarea disabled={locked} maxLength={1000} value={reason} onChange={e=>{setReason(e.target.value)}}/></label>}

      {selected&&<><h3>Itens registrados na venda</h3><ul>{selected.items?.map((i,n)=><li key={n}>{i.code} · {i.name} · {i.quantity}</li>)}</ul><h3>Receita preservada</h3>{!selected.has_prescription?<p>Venda sem receita vinculada.</p>:!selected.can_view_prescription||!clinicalRights.access?.prescriptions.view?<p>A receita está vinculada. Consulte com um usuário autorizado.</p>:selected.prescription?<div className="os-rx"><p>Receita #{selected.prescription.source_id} · versão {selected.prescription.source_version} · {selected.prescription.snapshot.prescriber_name||'Prescritor não informado'}</p><table><thead><tr><th>Olho</th><th>Esférico</th><th>Cilíndrico</th><th>Eixo</th><th>Adição</th><th>DNP</th></tr></thead><tbody>{(['od','oe'] as const).map(eye=><tr key={eye}><th>{eye.toUpperCase()}</th>{(['sphere','cylinder','axis','addition','dnp'] as const).map(field=><td key={field}>{String(selected.prescription?.snapshot[`${eye}_${field}`]??'—')}</td>)}</tr>)}</tbody></table><p>DP: {selected.prescription.snapshot.pd??'—'} · {selected.prescription.snapshot.notes}</p></div>:null}
      {(caps.advance&&selected.actions.advance||caps.rework&&selected.actions.rework||caps.cancel&&selected.actions.cancel)&&<fieldset disabled={locked}><legend>Próxima ação</legend><label className="os-check"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>Confirmo a conferência / entrega quando exigida</label><div className="os-actions">{caps.rework&&selected.actions.rework&&<><select aria-label="Destino do retrabalho" value={target} onChange={e=>setTarget(e.target.value as typeof target)}><option value="laboratory">Voltar ao laboratório</option><option value="mounting">Voltar à montagem</option></select><button type="button" onClick={()=>operation('rework')}>Registrar retrabalho</button></>}<button hidden={!caps.cancel||!selected.actions.cancel} type="button" className="os-danger" onClick={()=>{if(dirty){setError('Salve as alterações dos campos antes de cancelar a OS.');return}setCancelReview(true)}}>Cancelar OS</button></div><p className="os-hint">Use o campo de motivo acima para retrabalho, cancelamento e identificação de quem recebeu.</p></fieldset>}
      <h3>Histórico da OS</h3><div className="os-history">{selected.events?.map(e=><article key={e.version}><strong>{actions[e.action]} · {labels[e.to_status]}</strong><small>{dateTime.format(new Date(e.created_at))} · {e.creator_username} · versão {e.version}</small>{e.reason&&<p>{e.reason}</p>}<details><summary>Dados desta versão</summary><p>Previsão: {e.snapshot.promised_on} · Laboratório: {e.snapshot.laboratory||'—'}</p><p>{e.snapshot.frame_description} · {e.snapshot.lens_description}</p><p>{e.snapshot.notes}</p></details></article>)}</div><button type="button" disabled={locked||dirty} onClick={()=>void open(selected.id)}>Reabrir dados atuais</button></>}

      </div>}
    </FormDialog>}
    {cancelReview&&selected&&caps.cancel&&selected.actions.cancel&&<FormDialog title={`Cancelar OS #${selected.id}`} sectionLabel="OPERAÇÃO · CONFIRMAÇÃO" subtitle={selected.customer_name} busy={locked} onClose={()=>setCancelReview(false)}
      actions={<button type="button" className="erp-window-danger" disabled={locked||rights.loading||!reason.trim()} onClick={()=>{setCancelReview(false);operation('cancel')}}>Confirmar cancelamento da OS</button>}>
      <p>O cancelamento encerra a produção desta ordem. A venda e os pagamentos permanecem como estão.</p>
      <label className="erp-operation-reason">Motivo do cancelamento<textarea maxLength={1000} value={reason} disabled={locked} onChange={e=>setReason(e.target.value)} required/></label>
    </FormDialog>}
  </section>
}
