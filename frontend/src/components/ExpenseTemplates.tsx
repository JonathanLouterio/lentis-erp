import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { getExpenseTemplates, saveExpenseTemplate } from '../api'
import type { ExpenseTemplate, ExpenseTemplatePage, PayableOptions } from '../api'
import FormDialog from './FormDialog'
import { decimal, decimalText, failure, money } from './saleMoney'

type Categories = PayableOptions['expense_categories']

function useTemplates(storeId: number, includeArchived: boolean, search = '', reload = 0) {
  const [page, setPage] = useState(1)
  const [rows, setRows] = useState<ExpenseTemplatePage | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    void getExpenseTemplates(storeId, page, includeArchived, search).then(result => {
      if (active) { setRows(result); setError('') }
    }).catch(error => { if (active) { setRows(null); setError(failure(error)) } })
    return () => { active = false }
  }, [storeId, page, includeArchived, search, reload])
  return {page, setPage, rows, error}
}

export function ExpenseTemplatePicker({storeId, disabled, onApply}: {
  storeId:number; disabled:boolean; onApply:(template:ExpenseTemplate)=>void
}) {
  const {page, setPage, rows, error} = useTemplates(storeId, false)
  const [id, setId] = useState('')
  const [appliedName, setAppliedName] = useState('')
  const selected = rows?.results.find(template => String(template.id) === id)
  if (error) return <p className="payable-note" role="status">Não foi possível carregar os modelos. Você pode preencher a despesa manualmente.</p>
  if (!rows?.count) return null
  return <fieldset className="payable-template-box" disabled={disabled}>
    <legend>Preencher com um modelo</legend>
    <div className="payable-template-picker">
      <select aria-label="Modelo de despesa" value={id} onChange={event=>setId(event.target.value)}>
        <option value="">Selecione um modelo</option>
        {rows.results.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}
      </select>
      <button type="button" disabled={!selected} onClick={()=>{
        if (selected) { onApply(selected); setAppliedName(selected.name) }
      }}>Usar modelo</button>
    </div>
    {rows.previous || rows.next ? <div className="payable-heading-actions">
      <button type="button" disabled={!rows.previous} onClick={()=>{setId('');setPage(page-1)}}>Modelos anteriores</button>
      <button type="button" disabled={!rows.next} onClick={()=>{setId('');setPage(page+1)}}>Mais modelos</button>
    </div> : null}
    {appliedName && <p role="status">Modelo {appliedName} aplicado. Confira o valor e o vencimento antes de salvar.</p>}
  </fieldset>
}

type Props = {
  storeId: number
  storeName: string
  categories: Categories
  busy: boolean
  onBusyChange: (value:boolean)=>void
  onDirtyChange: (value:boolean)=>void
  onClose: ()=>void
}
type Draft = {name:string;category:string;description:string;payee:string;amount:string;dueDay:string;active:boolean}
const emptyDraft:Draft = {name:'',category:'',description:'',payee:'',amount:'',dueDay:'',active:true}

export default function ExpenseTemplates({storeId,storeName,categories,busy,onBusyChange,onDirtyChange,onClose}:Props) {
  const [search, setSearch] = useState('')
  const [reload, setReload] = useState(0)
  const {page, setPage, rows, error:loadError} = useTemplates(storeId,true,search,reload)
  const [editing, setEditing] = useState<ExpenseTemplate | 'new' | null>(null)
  const [draft, setDraft] = useState(emptyDraft)
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const amount = draft.amount.trim() ? decimal(draft.amount) : null
  const dueDay = draft.dueDay ? Number(draft.dueDay) : null
  const valid = !!draft.name.trim() && !!draft.category && !!draft.description.trim() &&
    (!draft.amount.trim() || (amount !== null && amount > 0n)) &&
    (dueDay === null || (Number.isInteger(dueDay) && dueDay >= 1 && dueDay <= 31))

  function change<T extends keyof Draft>(key:T,value:Draft[T]) {
    setDraft(current=>({...current,[key]:value}));setDirty(true);onDirtyChange(true)
  }
  function edit(row:ExpenseTemplate|'new') {
    if (busy || (dirty && !window.confirm('Descartar alterações deste modelo?'))) return
    setEditing(row)
    setDraft(row==='new' ? emptyDraft : {name:row.name,category:row.category,description:row.description,payee:row.payee,
      amount:row.suggested_amount?.replace('.',',') ?? '',dueDay:row.due_day?.toString() ?? '',active:row.active})
    setDirty(false);onDirtyChange(false);setError('');setSuccess('')
  }
  async function save(event:FormEvent) {
    event.preventDefault()
    if (!editing || !valid || busy) return
    onBusyChange(true);setError('');setSuccess('')
    try {
      const saved=await saveExpenseTemplate(storeId,{name:draft.name.trim(),category:draft.category,description:draft.description.trim(),
        payee:draft.payee.trim(),suggested_amount:amount===null?null:decimalText(amount),due_day:dueDay},
        editing==='new'?undefined:{id:editing.id,version:editing.version,active:draft.active})
      setEditing(null);setDirty(false);onDirtyChange(false);setReload(value=>value+1);setPage(1);setSearch('')
      setSuccess(saved.active?'Modelo salvo.':'Modelo arquivado.')
    } catch (error) { setError(failure(error));setReload(value=>value+1) }
    finally { onBusyChange(false) }
  }
  return <FormDialog wide title="Modelos de despesas" subtitle={storeName} sectionLabel="FINANCEIRO · CONTAS A PAGAR"
    busy={busy} dirty={dirty} onClose={onClose} notice={error || success}>
    <div className="payable-main">
      <p>Salve os dados que se repetem nas contas da unidade. O modelo só preenche o formulário: cada despesa é conferida e salva por você.</p>
      {success && <p className="payable-success" role="status">{success}</p>}
      {error && <p className="erp-alert" role="alert">{error}</p>}
      {!editing && <>
      <div className="payable-toolbar">
        <label>Buscar modelo<input value={search} maxLength={100} onChange={event=>{setSearch(event.target.value);setPage(1)}} disabled={busy} /></label>
        <button type="button" className="erp-action-button" onClick={()=>edit('new')} disabled={busy}>Novo modelo</button>
      </div>
      {loadError && <p className="erp-alert" role="alert">{loadError}</p>}
      {!loadError && !rows && <p role="status">Carregando modelos…</p>}
      {rows?.results.map(row=><button type="button" className="payable-row" key={row.id} onClick={()=>edit(row)} disabled={busy}>
        <strong>{row.name}</strong><span>{row.category_label} · {row.active?'Ativo':'Arquivado'}</span>
        <small>{row.suggested_amount ? money.format(Number(row.suggested_amount)) : 'Valor a informar'} · {row.due_day ? `Dia ${row.due_day}` : 'Vencimento a informar'}</small>
      </button>)}
      {rows && !rows.count && <p>Nenhum modelo encontrado.</p>}
      {rows && (rows.previous || rows.next) && <div className="payable-pagination">
        <button type="button" disabled={busy||!rows.previous} onClick={()=>setPage(page-1)}>Anterior</button>
        <span>Página {page}</span>
        <button type="button" disabled={busy||!rows.next} onClick={()=>setPage(page+1)}>Próxima</button>
      </div>}
      </>}
      {editing && <form className="erp-finance-form payable-template-box" onSubmit={save}>
        <fieldset disabled={busy}>
          <legend>{editing==='new'?'Novo modelo':`Editar modelo: ${editing.name}`}</legend>
          <label>Nome do modelo<input required maxLength={100} value={draft.name} onChange={e=>change('name',e.target.value)} /></label>
          <label>Categoria<select aria-label="Categoria do modelo" required value={draft.category} onChange={e=>change('category',e.target.value)}>
            <option value="">Selecione</option>{categories.map(category=><option key={category.value} value={category.value}>{category.label}</option>)}
          </select></label>
          <label>Descrição da despesa<input required maxLength={160} value={draft.description} onChange={e=>change('description',e.target.value)} /></label>
          <div className="payable-fields">
            <label>Favorecido (opcional)<input maxLength={140} value={draft.payee} onChange={e=>change('payee',e.target.value)} /></label>
            <label>Valor sugerido (R$, opcional)<input inputMode="decimal" value={draft.amount} onChange={e=>change('amount',e.target.value)} /></label>
            <label>Dia do vencimento (opcional)<input type="number" min={1} max={31} value={draft.dueDay} onChange={e=>change('dueDay',e.target.value)} /></label>
          </div>
          {editing!=='new' && <label className="payable-check"><input type="checkbox" checked={draft.active} onChange={e=>change('active',e.target.checked)} />Modelo ativo</label>}
          <div className="payable-heading-actions">
            <button type="submit" className="erp-action-button" disabled={!valid||busy}>Salvar modelo</button>
            <button type="button" onClick={()=>{
              if (dirty && !window.confirm('Descartar alterações deste modelo?')) return
              setEditing(null);setDirty(false);onDirtyChange(false);setError('')
            }}>Voltar à lista</button>
          </div>
        </fieldset>
      </form>}
    </div>
  </FormDialog>
}
