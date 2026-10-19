import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError, getSupplier, getSuppliers, submitSupplier } from '../api'
import type { AccessibleStore, Supplier, SupplierAttempt, SupplierPayload, SuppliersPage } from '../api'
import { dateTime, failure } from './saleMoney'
import './Suppliers.css'

type Props={store:AccessibleStore;userId:number;onSavingChange:(v:boolean)=>void;onDirtyChange:(v:boolean)=>void}
const blank=():SupplierPayload=>({person_type:'company',name:'',trade_name:'',document:'',state_registration:'',contact_name:'',phone:'',whatsapp:'',email:'',zip_code:'',street:'',address_number:'',address_complement:'',neighborhood:'',city:'',state:'',notes:''})
const empty:SuppliersPage={count:0,next:null,previous:null,results:[],can_create:false,can_edit:false}
const fields:{key:Exclude<keyof SupplierPayload,'person_type'|'notes'>;label:string;max:number;type?:string}[]=[
  {key:'name',label:'Nome / razão social',max:180},{key:'trade_name',label:'Nome fantasia',max:180},{key:'document',label:'CPF / CNPJ',max:32},{key:'state_registration',label:'Inscrição estadual / RG',max:30},
  {key:'contact_name',label:'Pessoa de contato',max:150},{key:'phone',label:'Telefone',max:30},{key:'whatsapp',label:'WhatsApp',max:30},{key:'email',label:'E-mail',max:254,type:'email'},
  {key:'zip_code',label:'CEP',max:9},{key:'street',label:'Logradouro',max:150},{key:'address_number',label:'Número',max:20},{key:'address_complement',label:'Complemento',max:100},
  {key:'neighborhood',label:'Bairro',max:100},{key:'city',label:'Cidade',max:100},{key:'state',label:'UF',max:2},
]

export default function Suppliers({store,userId,onSavingChange,onDirtyChange}:Props){
  const storageKey=`lentis.supplier.${userId}.${store.id}`
  const [result,setResult]=useState(empty)
  const [search,setSearch]=useState('')
  const [query,setQuery]=useState('')
  const [status,setStatus]=useState('active')
  const [page,setPage]=useState(1)
  const [reload,setReload]=useState(0)
  const [selected,setSelected]=useState<Supplier|null>(null)
  const [editor,setEditor]=useState(false)
  const [form,setForm]=useState(blank)
  const [reason,setReason]=useState('')
  const [dirty,setDirty]=useState(false)
  const [busy,setBusy]=useState(false)
  const [loading,setLoading]=useState(true)
  const [error,setError]=useState('')
  const [success,setSuccess]=useState('')
  const [pending,setPending]=useState<SupplierAttempt|null>(()=>{try{return JSON.parse(sessionStorage.getItem(storageKey)||'null') as SupplierAttempt|null}catch{return null}})
  const locked=busy||!!pending
  const editable=selected?result.can_edit:result.can_create
  useEffect(()=>{onSavingChange(busy);return()=>onSavingChange(false)},[busy,onSavingChange])
  useEffect(()=>{onDirtyChange(dirty||!!reason||!!pending);return()=>onDirtyChange(false)},[dirty,reason,pending,onDirtyChange])
  useEffect(()=>{const warn=(e:BeforeUnloadEvent)=>{if(dirty||reason||pending)e.preventDefault()};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn)},[dirty,reason,pending])
  useEffect(()=>{
    let ignore=false;setLoading(true);setError('');setResult(v=>({...v,results:[],count:0,next:null,previous:null}))
    void getSuppliers(store.id,page,status,query).then(v=>{if(!ignore)setResult(v)}).catch(e=>{if(!ignore){setError(failure(e));setResult(empty);setSelected(null);setEditor(false)}}).finally(()=>{if(!ignore)setLoading(false)})
    return()=>{ignore=true}
  },[store.id,page,status,query,reload])
  function allowed(){return !dirty&&!reason||window.confirm('Descartar as alterações não salvas do fornecedor?')}
  function accept(s:Supplier){setSelected(s);setForm(Object.fromEntries(Object.keys(blank()).map(k=>[k,s[k as keyof SupplierPayload]])) as SupplierPayload);setEditor(true);setReason('');setDirty(false)}
  async function open(id:number){if(locked||!allowed())return;setBusy(true);setError('');try{accept(await getSupplier(store.id,id))}catch(e){setError(failure(e));setSelected(null);setEditor(false)}finally{setBusy(false)}}
  function newSupplier(){if(locked||!allowed())return;setSelected(null);setForm(blank());setReason('');setDirty(false);setEditor(true);setError('');setSuccess('')}
  async function send(attempt:SupplierAttempt){
    if(busy)return
    setBusy(true);setPending(attempt);setError('');setSuccess('')
    try{sessionStorage.setItem(storageKey,JSON.stringify(attempt))}catch{/* Identificador mantido na memória desta tela. */}
    try{const supplier=await submitSupplier(store.id,attempt);setPending(null);try{sessionStorage.removeItem(storageKey)}catch{/* Sem armazenamento disponível. */}accept(supplier);setReload(v=>v+1);setSuccess('Fornecedor salvo. Registro e histórico atualizados.')}
    catch(e){setError(failure(e));if(e instanceof ApiError&&e.status>=400&&e.status<500){setPending(null);try{sessionStorage.removeItem(storageKey)}catch{/* Sem armazenamento disponível. */}}}
    finally{setBusy(false)}
  }
  function save(e:FormEvent){e.preventDefault();if(locked)return;void send({id:selected?.id??null,payload:{...form,request_id:crypto.randomUUID(),action:selected?'update':'create',...(selected?{expected_version:selected.version}:{}),reason}})}
  function transition(){if(!selected||locked)return;if(dirty){setError('Salve as alterações dos campos antes de mudar a situação.');return}if(!reason.trim()){setError('Informe o motivo da inativação ou reativação.');return}const action=selected.is_active?'archive':'restore';if(!window.confirm(`${selected.is_active?'Inativar':'Reativar'} ${selected.name}?`))return;void send({id:selected.id,payload:{request_id:crypto.randomUUID(),action,expected_version:selected.version,reason}})}
  function searchSubmit(e:FormEvent){e.preventDefault();setQuery(search);setPage(1)}
  return <section className="supplier-page">
    <header className="supplier-heading"><div><span className="erp-kicker">CADASTROS · {store.name}</span><h1>Fornecedores</h1><p>Dados fiscais, contato e endereço para suas próximas compras.</p></div><button className="erp-action-button" type="button" disabled={locked||!result.can_create} onClick={newSupplier}>Novo fornecedor</button></header>
    {error&&<p className="erp-alert" role="alert">{error}</p>}{success&&<p className="supplier-success" role="status">{success}</p>}
    {pending&&<div className="erp-card"><h2>Conferir envio pendente</h2><p>A resposta não foi confirmada. Repita o mesmo envio para recuperar o resultado sem duplicar o cadastro ou a alteração.</p><button type="button" className="erp-action-button" disabled={busy} onClick={()=>void send(pending)}>Conferir / repetir envio</button></div>}
    <form onSubmit={searchSubmit} className="supplier-toolbar"><label>Buscar fornecedores<input value={search} disabled={locked} onChange={e=>setSearch(e.target.value)} placeholder="Nome, CPF/CNPJ, contato ou e-mail"/></label><button type="submit" disabled={locked}>Buscar</button><label>Situação<select aria-label="Situação dos fornecedores" value={status} disabled={locked} onChange={e=>{setStatus(e.target.value);setPage(1)}}><option value="active">Ativos</option><option value="inactive">Inativos</option><option value="all">Todos</option></select></label><button type="button" disabled={locked} onClick={()=>setReload(v=>v+1)}>Atualizar lista</button></form>
    <div className="supplier-grid"><div className="erp-card supplier-list"><h2>Cadastros <small>({result.count})</small></h2>{loading?<p role="status">Carregando fornecedores…</p>:!result.results.length?<p>Nenhum fornecedor neste filtro.</p>:result.results.map(s=><button type="button" className={`supplier-row${selected?.id===s.id?' is-selected':''}`} key={s.id} disabled={locked} onClick={()=>void open(s.id)}><strong>{s.name}</strong><span>{s.document||'Documento não informado'} · {s.is_active?'Ativo':'Inativo'}</span><small>{[s.contact_name,s.phone,s.city,s.state].filter(Boolean).join(' · ')||'Contato não informado'}</small></button>)}<div className="supplier-pagination"><button type="button" disabled={locked||!result.previous} onClick={()=>setPage(v=>v-1)}>Anterior</button><span>Página {page}</span><button type="button" disabled={locked||!result.next} onClick={()=>setPage(v=>v+1)}>Próxima</button></div></div>
    <div className="erp-card supplier-detail">{!editor?<><h2>Cadastro de fornecedores</h2><p>Selecione um fornecedor para consultar ou editar seus dados.</p></>:<><h2>{selected?selected.name:'Novo fornecedor'}</h2>{selected&&<p className="supplier-hint">{selected.is_active?'Ativo':'Inativo'} · Código #{selected.id} · versão {selected.version}</p>}
    <form onSubmit={save}><fieldset disabled={locked||!editable}><legend>Identificação, contato e endereço</legend><label>Tipo de pessoa<select aria-label="Tipo de pessoa do fornecedor" value={form.person_type} onChange={e=>{setForm({...form,person_type:e.target.value as SupplierPayload['person_type'],document:''});setDirty(true)}}><option value="company">Pessoa jurídica</option><option value="individual">Pessoa física</option></select></label><div className="supplier-fields">{fields.map(f=><label key={f.key}>{f.label}<input type={f.type||'text'} required={f.key==='name'} maxLength={f.max} value={form[f.key]} onChange={e=>{setForm({...form,[f.key]:f.key==='state'?e.target.value.toUpperCase():e.target.value});setDirty(true)}} placeholder={f.key==='document'?(form.person_type==='company'?'CNPJ numérico ou alfanumérico':'CPF'):undefined}/></label>)}</div><p className="supplier-hint">CPF/CNPJ é opcional; se informado, precisa ser válido e não pode repetir nesta unidade, mesmo em cadastro inativo.</p><label>Observações<textarea maxLength={4000} value={form.notes} onChange={e=>{setForm({...form,notes:e.target.value});setDirty(true)}}/></label><button type="submit" className="erp-action-button">{busy?'Salvando…':selected?'Salvar alterações':'Cadastrar fornecedor'}</button></fieldset></form>
    {selected&&<><fieldset disabled={locked||!result.can_edit}><legend>Situação e motivo</legend><label>Motivo / observação da operação<textarea maxLength={255} value={reason} onChange={e=>setReason(e.target.value)}/></label><p className="supplier-hint">O motivo é obrigatório para inativar ou reativar. Alterações dos campos devem ser salvas antes.</p><button type="button" className="erp-secondary-button" onClick={transition}>{selected.is_active?'Inativar fornecedor':'Reativar fornecedor'}</button></fieldset><h3>Histórico de operações</h3><div className="supplier-history">{selected.events?.map(e=><article key={e.version}><strong>{e.action_label} · versão {e.version}</strong><small>{dateTime.format(new Date(e.created_at))} · {e.creator_username}</small>{e.reason&&<p>{e.reason}</p>}</article>)}</div><button type="button" disabled={locked} onClick={()=>void open(selected.id)}>Reabrir dados atuais</button></>}
    </>}</div></div>
  </section>
}
