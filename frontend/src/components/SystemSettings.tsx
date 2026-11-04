import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError, getSystemCompanies, getSystemCompany, getSystemStores, getConfigurationHistory, saveSystemCompany, saveSystemStore } from '../api'
import type { CompanySettings, StoreSettings, ConfigurationPage, ConfigurationEvent, CompanySettingsInput, StoreSettingsInput } from '../api'
import FormDialog from './FormDialog'
import './SystemSettings.css'

type Props = { onSavingChange: (value: boolean) => void; onDirtyChange: (value: boolean) => void; onSaved: () => void }
type Draft = {
  name: string; legal_name: string; email: string; phone: string; address: string; city: string; state: string
  website: string; instagram: string; facebook: string; tiktok: string; whatsapp: string
  code: string; is_active: boolean; allow_negative_stock: boolean
}
type Editor = { kind: 'company' | 'store'; id: number | null; version?: number; companyId?: number; companyName?: string; original: Draft }
const blank: Draft = { name: '', legal_name: '', email: '', phone: '', address: '', city: '', state: '', website: '', instagram: '', facebook: '', tiktok: '', whatsapp: '', code: '', is_active: true, allow_negative_stock: true }
const labels: Record<string, string> = { name: 'Nome', legal_name: 'Razão social', email: 'E-mail', phone: 'Telefone', address: 'Endereço', city: 'Cidade', state: 'UF', website: 'Site', instagram: 'Instagram', facebook: 'Facebook', tiktok: 'TikTok', whatsapp: 'WhatsApp', code: 'Código', is_active: 'Ativa', allow_negative_stock: 'Estoque negativo' }
const actionLabels: Record<string, string> = { company_created: 'Ótica cadastrada', company_updated: 'Ótica atualizada', store_created: 'Unidade cadastrada', store_updated: 'Unidade atualizada' }
const states = 'AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split(' ')
const message = (error: unknown) => error instanceof Error ? error.message : 'Não foi possível concluir a operação.'
const valueText = (value: unknown) => value === true ? 'Sim' : value === false ? 'Não' : value == null || value === '' ? 'Não informado' : String(value)
function draftOf(record?: CompanySettings | StoreSettings): Draft {
  const result = { ...blank }
  if (record) for (const key of Object.keys(blank) as (keyof Draft)[]) {
    if (key in record) Object.assign(result, { [key]: record[key as keyof typeof record] })
  }
  return result
}
function Pager({ page, next, onChange }: { page: number; next: boolean; onChange: (page: number) => void }) {
  return <div className="sys-pagination"><button type="button" disabled={page <= 1} onClick={() => onChange(page - 1)}>Anterior</button><span>Página {page}</span><button type="button" disabled={!next} onClick={() => onChange(page + 1)}>Próxima</button></div>
}

export default function SystemSettings({ onSavingChange, onDirtyChange, onSaved }: Props) {
  const [companies, setCompanies] = useState<ConfigurationPage<CompanySettings> | null>(null)
  const [selected, setSelected] = useState<CompanySettings | null>(null)
  const [stores, setStores] = useState<ConfigurationPage<StoreSettings> | null>(null)
  const [history, setHistory] = useState<ConfigurationPage<ConfigurationEvent> | null>(null)
  const [page, setPage] = useState(1), [storePage, setStorePage] = useState(1), [historyPage, setHistoryPage] = useState(1)
  const [query, setQuery] = useState(''), [search, setSearch] = useState('')
  const [reload, setReload] = useState(0), [loading, setLoading] = useState(true), [detailLoading, setDetailLoading] = useState(false)
  const [loadError, setLoadError] = useState(''), [detailError, setDetailError] = useState('')
  const [success, setSuccess] = useState(''), [editor, setEditor] = useState<Editor | null>(null)
  const [draft, setDraft] = useState<Draft>({ ...blank }), [error, setError] = useState('')
  const [saving, setSaving] = useState(false), [conflict, setConflict] = useState(false), [tab, setTab] = useState<'data' | 'social'>('data')
  const requestId = useRef(''), sending = useRef(false)
  const callbacks = useRef({ onSavingChange, onDirtyChange, onSaved })
  callbacks.current = { onSavingChange, onDirtyChange, onSaved }
  const dirty = !!editor && JSON.stringify(draft) !== JSON.stringify(editor.original)
  useEffect(() => { callbacks.current.onDirtyChange(dirty) }, [dirty])
  useEffect(() => () => { callbacks.current.onDirtyChange(false); callbacks.current.onSavingChange(false) }, [])
  useEffect(() => {
    let ignore = false
    setLoading(true); setLoadError('')
    void getSystemCompanies(search, page).then(data => { if (!ignore) setCompanies(data) })
      .catch(err => { if (!ignore) { setLoadError(message(err)); setCompanies(null); setSelected(null) } })
      .finally(() => { if (!ignore) setLoading(false) })
    return () => { ignore = true }
  }, [search, page, reload])
  const selectedId = selected?.id
  useEffect(() => {
    let ignore = false
    setStores(null); setHistory(null); setDetailError('')
    if (!selectedId) return
    setDetailLoading(true)
    void Promise.all([getSystemStores(selectedId, storePage), getConfigurationHistory(selectedId, historyPage), getSystemCompany(selectedId)])
      .then(([units, events, company]) => { if (!ignore) { setStores(units); setHistory(events); setSelected(company) } })
      .catch(err => { if (!ignore) setDetailError(message(err)) })
      .finally(() => { if (!ignore) setDetailLoading(false) })
    return () => { ignore = true }
  }, [selectedId, storePage, historyPage, reload])
  function selectCompany(company: CompanySettings) { setSelected(company); setStorePage(1); setHistoryPage(1); setSuccess('') }
  function open(kind: Editor['kind'], record?: CompanySettings | StoreSettings) {
    const initial = draftOf(record)
    setDraft(initial); setEditor({ kind, id: record?.id ?? null, version: record?.version, companyId: selected?.id, companyName: selected?.name, original: initial })
    requestId.current = crypto.randomUUID(); setError(''); setConflict(false); setTab('data'); setSuccess('')
  }
  function change<K extends keyof Draft>(key: K, value: Draft[K]) {
    requestId.current = crypto.randomUUID(); setDraft(current => ({ ...current, [key]: value })); setError('')
  }
  function close() { if (!sending.current) { setEditor(null); setError('') } }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!editor || sending.current || conflict) return
    const form = event.currentTarget
    if (!form.checkValidity()) {
      const invalid = form.querySelector<HTMLInputElement>(':invalid')
      setTab(['website', 'instagram', 'facebook', 'tiktok', 'whatsapp'].includes(invalid?.name || '') ? 'social' : 'data')
      requestAnimationFrame(() => form.reportValidity())
      return
    }
    if (editor.id !== null && editor.original.is_active && !draft.is_active && !window.confirm(editor.kind === 'company' ? 'Inativar esta ótica? Todas as suas unidades ficarão indisponíveis para operação.' : 'Inativar esta unidade? Seus usuários perderão o acesso operacional a ela.')) return
    sending.current = true; setSaving(true); callbacks.current.onSavingChange(true); setError('')
    const common = { name: draft.name, email: draft.email, phone: draft.phone, address: draft.address, city: draft.city, state: draft.state, is_active: draft.is_active, request_id: requestId.current, ...(editor.version ? { version: editor.version } : {}) }
    try {
      if (editor.kind === 'company') {
        const payload: CompanySettingsInput = { ...common, legal_name: draft.legal_name, website: draft.website, instagram: draft.instagram, facebook: draft.facebook, tiktok: draft.tiktok, whatsapp: draft.whatsapp }
        const company = await saveSystemCompany(editor.id, payload)
        setSelected(company); setStorePage(1); setHistoryPage(1)
        if (editor.id === null) { setSearch(''); setQuery(''); setPage(1) }
      } else {
        const payload: StoreSettingsInput = { ...common, company_id: editor.companyId!, code: draft.code, allow_negative_stock: draft.allow_negative_stock }
        await saveSystemStore(editor.id, payload)
      }
      setEditor(null); setSuccess('Cadastro salvo. O histórico e as unidades disponíveis foram atualizados.')
      setReload(value => value + 1); callbacks.current.onSaved()
    } catch (err) {
      setError(message(err)); if (err instanceof ApiError && (err.status === 409 || err.status === 403)) setConflict(true)
    } finally { sending.current = false; setSaving(false); callbacks.current.onSavingChange(false) }
  }
  function field(key: keyof Draft, type = 'text', maxLength = 150, required = false) {
    return <label key={key}>{labels[key]}{required ? ' *' : ''}<input name={key} type={type} value={String(draft[key])} maxLength={maxLength} required={required} onChange={event => change(key, event.target.value)} /></label>
  }
  return <section className="system-settings">
    <header className="sys-heading"><div><span className="sys-eyebrow">ADMINISTRAÇÃO GLOBAL</span><h1>Configurações do sistema</h1><p>Organize suas óticas, unidades e canais de contato.</p></div><div className="sys-heading-actions"><button type="button" disabled={loading} onClick={() => setReload(value => value + 1)}>Atualizar</button><button className="sys-primary" type="button" disabled={loading || !!loadError} onClick={() => open('company')}>+ Nova ótica</button></div></header>
    <p className="sys-notice">Acesso exclusivo do administrador global. O acesso dos demais usuários às unidades é definido em <strong>Usuários e permissões</strong>.</p>
    {success && <p className="sys-success" role="status">{success}</p>}
    {loadError && <div className="sys-error" role="alert">{loadError} <button type="button" onClick={() => setReload(value => value + 1)}>Tentar novamente</button></div>}
    <div className="sys-grid">
      <aside className="sys-card sys-companies" aria-label="Óticas cadastradas"><div className="sys-card-heading"><h2>Óticas</h2><span>{companies?.count ?? '—'}</span></div>
        <form className="sys-search" onSubmit={event => { event.preventDefault(); setPage(1); setSearch(query); setSelected(null) }}><label className="sys-sr-only" htmlFor="company-search">Buscar ótica</label><input id="company-search" maxLength={150} placeholder="Buscar pelo nome…" value={query} onChange={event => setQuery(event.target.value)} /><button type="submit">Buscar</button></form>
        {loading ? <p role="status">Carregando óticas…</p> : companies?.results.length ? <ul>{companies.results.map(company => <li key={company.id}><button type="button" className={selectedId === company.id ? 'is-selected' : ''} aria-pressed={selectedId === company.id} onClick={() => selectCompany(company)}><strong>{company.name}</strong><span>{company.city ? `${company.city}${company.state ? ` · ${company.state}` : ''}` : 'Localização não informada'}</span><small className={`sys-status ${company.is_active ? '' : 'is-inactive'}`}>{company.is_active ? 'Ativa' : 'Inativa'}</small></button></li>)}</ul> : !loadError && <p className="sys-empty">{search ? 'Nenhuma ótica encontrada.' : 'Cadastre a primeira ótica para começar.'}</p>}
        {companies && <Pager page={page} next={companies.has_next} onChange={setPage} />}
      </aside>
      <div className="sys-detail">{!selected ? <div className="sys-card sys-empty"><span className="sys-empty-icon" aria-hidden="true">⌂</span><h2>Sua operação começa aqui</h2><p>Selecione uma ótica para gerenciar suas unidades e informações.</p></div> : <>
        <article className="sys-card"><div className="sys-card-heading"><div><span className="sys-eyebrow">ÓTICA / EMPRESA</span><h2>{selected.name}</h2></div><button type="button" onClick={() => open('company', selected)}>Editar ótica</button></div><p>{selected.legal_name || 'Razão social não informada'}</p>
          {!selected.is_active && <p className="sys-warning">Ótica inativa: suas unidades estão indisponíveis para operação. Reativar a ótica restaura o acesso às unidades e vínculos que continuarem ativos.</p>}
          <dl className="sys-summary"><div><dt>Contato</dt><dd>{selected.phone || selected.email || 'Não informado'}</dd></div><div><dt>Localização</dt><dd>{[selected.city, selected.state].filter(Boolean).join(' / ') || 'Não informada'}</dd></div></dl>
          <div className="sys-social">{(['website', 'instagram', 'facebook', 'tiktok'] as const).map(key => selected[key] ? <a key={key} href={selected[key]} target="_blank" rel="noopener noreferrer">{labels[key]} ↗</a> : null)}{selected.whatsapp && <span>WhatsApp: +{selected.whatsapp}</span>}</div>
        </article>
        <article className="sys-card"><div className="sys-card-heading"><div><h2>Unidades</h2><p>{stores ? `${stores.count} unidade(s) vinculada(s)` : 'Lojas desta ótica'}</p></div><button className="sys-primary" type="button" disabled={!selected.is_active || detailLoading || !!detailError} onClick={() => open('store')}>+ Nova unidade</button></div>
          {detailLoading ? <p role="status">Carregando unidades e histórico…</p> : detailError ? <div className="sys-error" role="alert">{detailError} <button type="button" onClick={() => setReload(value => value + 1)}>Tentar novamente</button></div> : stores?.results.length ? <div className="sys-units">{stores.results.map(store => <div className="sys-unit" key={store.id}><div><span className="sys-code">{store.code}</span><strong>{store.name}</strong><span>{[store.city, store.state].filter(Boolean).join(' / ') || 'Localização não informada'}</span></div><div className="sys-unit-actions"><span className={`sys-status ${store.is_active && selected.is_active ? '' : 'is-inactive'}`}>{!selected.is_active ? 'Ótica inativa' : store.is_active ? 'Ativa' : 'Inativa'}</span><button type="button" onClick={() => open('store', store)}>Editar</button></div></div>)}</div> : <p className="sys-empty">Nenhuma unidade cadastrada para esta ótica.</p>}
          {stores && <Pager page={storePage} next={stores.has_next} onChange={setStorePage} />}
        </article>
        <article className="sys-card"><div className="sys-card-heading"><h2>Histórico de alterações</h2><span>{history?.count ?? '—'}</span></div><p className="sys-muted">Registros realizados por esta área a partir de sua implantação.</p>
          {history?.results.length ? <ol className="sys-history">{history.results.map(item => <li key={item.id}><strong>{actionLabels[item.action] || item.action}{item.store_name ? ` · ${item.store_name}` : ''}</strong><span>{item.actor} · {new Date(item.created_at).toLocaleString('pt-BR')}</span><details><summary>Ver alterações ({Object.keys(item.changes).length})</summary><dl>{Object.entries(item.changes).map(([key, change]) => <div key={key}><dt>{labels[key] || key}</dt><dd>{valueText(change.before)} → {valueText(change.after)}</dd></div>)}</dl></details></li>)}</ol> : !detailLoading && !detailError && <p>Nenhuma alteração registrada.</p>}
          {history && <Pager page={historyPage} next={history.has_next} onChange={setHistoryPage} />}
        </article>
      </>}</div>
    </div>
    {editor && <FormDialog title={`${editor.id === null ? 'Nova' : 'Editar'} ${editor.kind === 'company' ? 'ótica' : 'unidade'}`} sectionLabel="CONFIGURAÇÕES" subtitle={editor.kind === 'store' ? `Ótica: ${editor.companyName}. O vínculo da unidade é permanente.` : 'Identidade, contato e presença digital da sua ótica.'} busy={saving} dirty={dirty} notice={error} onClose={close} actions={<button className="sys-primary erp-action-button" type="submit" form="system-config-form" disabled={saving || conflict}>{saving ? 'Salvando…' : 'Salvar cadastro'}</button>}>
      <div className="system-settings sys-editor">
        {error && <p className="sys-error" role="alert">{error}{conflict && ' Feche a janela e atualize a lista antes de tentar novamente.'}</p>}
        {editor.kind === 'company' && <nav className="system-tabs" aria-label="Seções do cadastro"><button type="button" aria-current={tab === 'data' ? 'page' : undefined} disabled={saving} onClick={() => setTab('data')}>Dados da ótica</button><button type="button" aria-current={tab === 'social' ? 'page' : undefined} disabled={saving} onClick={() => setTab('social')}>Redes sociais</button></nav>}
        <form id="system-config-form" onSubmit={save} noValidate>
          <fieldset disabled={saving || conflict}>
            <legend className="sys-sr-only">Cadastro</legend>
            <div className="sys-fields" hidden={tab !== 'data'}>
              {field('name', 'text', 150, true)}{editor.kind === 'company' ? field('legal_name', 'text', 200) : field('code', 'text', 10, true)}
              {field('email', 'email', 254)}{field('phone', 'tel', 30)}
              <div className="sys-full">{field('address', 'text', 250)}</div>{field('city', 'text', 100)}
              <label>UF<select value={draft.state} onChange={event => change('state', event.target.value)}><option value="">Selecione</option>{states.map(uf => <option key={uf} value={uf}>{uf}</option>)}</select></label>
              <label className="sys-check sys-full"><input type="checkbox" checked={draft.is_active} onChange={event => change('is_active', event.target.checked)} /><span>{editor.kind === 'company' ? 'Ótica ativa' : 'Unidade ativa'}<small>Inativar bloqueia o uso operacional e mantém os cadastros e históricos.</small></span></label>
              {!draft.is_active && editor.original.is_active && <p className="sys-warning sys-full">Ao salvar, {editor.kind === 'company' ? 'todas as unidades desta ótica ficarão indisponíveis' : 'esta unidade ficará indisponível'} nas próximas requisições, inclusive em sessões já abertas.</p>}
              {editor.kind === 'store' && <><label className="sys-check sys-full"><input type="checkbox" checked={draft.allow_negative_stock} onChange={event => change('allow_negative_stock', event.target.checked)} /><span>Permitir estoque negativo<small>Controla novas saídas e vendas conforme as regras de estoque existentes. Não modifica saldos já registrados.</small></span></label><p className="sys-muted sys-full">O código deve ser único em todo o sistema. Após cadastrar, vincule os usuários autorizados em Usuários e permissões.</p></>}
            </div>
            {editor.kind === 'company' && <div className="sys-fields" hidden={tab !== 'social'}><p className="sys-muted sys-full">Use o endereço completo com https://. Os canais pertencem à ótica e são compartilhados por suas unidades.</p>{field('website', 'url', 300)}{field('instagram', 'url', 300)}{field('facebook', 'url', 300)}{field('tiktok', 'url', 300)}{field('whatsapp', 'tel', 20)}<p className="sys-muted">WhatsApp com DDI e DDD. Exemplo: +55 41 99999-9999.</p></div>}
          </fieldset>
        </form>
      </div>
    </FormDialog>}
  </section>
}
