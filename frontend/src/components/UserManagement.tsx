import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  ApiError, getManagedUser, getManagedUserHistory, getManagedUsers, getUserManagementOptions,
  resetManagedUserPassword, saveManagedUser,
} from '../api'
import type {
  ManagedUser, ManagedUserPayload, ManagedUsersPage, UserAccessEvent, UserManagementOptions,
} from '../api'
import './UserManagement.css'

type Props = { onSavingChange: (saving: boolean) => void; onDirtyChange: (dirty: boolean) => void }
const blank = (): ManagedUserPayload => ({
  username: '', first_name: '', last_name: '', email: '', is_active: true,
  permission_ids: [], memberships: [],
})
const message = (err: unknown) => err instanceof Error ? err.message : 'Não foi possível concluir a operação.'
const actions: Record<string, string> = { created: 'Cadastro criado', updated: 'Cadastro e acessos atualizados', password_reset: 'Senha redefinida' }
const fields: Record<string, string> = { username: 'Usuário', first_name: 'Nome', last_name: 'Sobrenome', email: 'E-mail', is_active: 'Situação', is_staff: 'Acesso ao Django Admin', is_superuser: 'Administrador', permission_ids: 'Permissões diretas', group_ids: 'Grupos', group_permission_ids: 'Permissões de grupos', memberships: 'Vínculos com lojas' }

export default function UserManagement({ onSavingChange, onDirtyChange }: Props) {
  const [options, setOptions] = useState<UserManagementOptions | null>(null)
  const [listing, setListing] = useState<ManagedUsersPage | null>(null)
  const [search, setSearch] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')
  const [page, setPage] = useState(1)
  const [retry, setRetry] = useState(0)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [editing, setEditing] = useState(false)
  const [record, setRecord] = useState<ManagedUser | null>(null)
  const [form, setForm] = useState<ManagedUserPayload>(blank)
  const [password, setPassword] = useState('')
  const [resetPassword, setResetPassword] = useState('')
  const [dirty, setDirty] = useState(false)
  const [permissionSearch, setPermissionSearch] = useState('')
  const [history, setHistory] = useState<UserAccessEvent[] | null>(null)
  const [showReset, setShowReset] = useState(false)
  const locked = loading || busy
  const protectedUser = record?.protected === true

  useEffect(() => { onSavingChange(busy); return () => onSavingChange(false) }, [busy, onSavingChange])
  useEffect(() => { onDirtyChange(dirty || !!resetPassword); return () => onDirtyChange(false) }, [dirty, resetPassword, onDirtyChange])
  useEffect(() => {
    if (!dirty && !busy && !resetPassword) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty, busy, resetPassword])
  useEffect(() => {
    let ignore = false
    setLoading(true); setError('')
    void Promise.all([getUserManagementOptions(), getManagedUsers(appliedSearch, page)])
      .then(([choices, users]) => { if (!ignore) { setOptions(choices); setListing(users) } })
      .catch(err => { if (!ignore) setError(message(err)) })
      .finally(() => { if (!ignore) setLoading(false) })
    return () => { ignore = true }
  }, [appliedSearch, page, retry])

  function mayLeave() {
    return (!dirty && !resetPassword) || window.confirm('Descartar as alterações não salvas deste usuário?')
  }
  function populate(user: ManagedUser) {
    setRecord(user)
    setForm({ username: user.username, first_name: user.first_name, last_name: user.last_name,
      email: user.email, is_active: user.is_active, permission_ids: user.permission_ids,
      memberships: user.memberships, version: user.version })
    setPassword(''); setResetPassword(''); setDirty(false); setShowReset(false)
    setEditing(true); setHistory(null); setPermissionSearch('')
  }
  async function openUser(id: number) {
    if (locked || !mayLeave()) return
    setBusy(true); setError(''); setSuccess('')
    try { populate(await getManagedUser(id)) } catch (err) { setError(message(err)) }
    finally { setBusy(false) }
  }
  function newUser() {
    if (locked || !mayLeave()) return
    setRecord(null); setForm(blank()); setPassword(''); setResetPassword(''); setDirty(false)
    setEditing(true); setHistory(null); setShowReset(false); setError(''); setSuccess(''); setPermissionSearch('')
  }
  function closeEditor() {
    setEditing(false); setDirty(false); setPassword(''); setResetPassword(''); setError(''); setSuccess('')
  }
  function change(patch: Partial<ManagedUserPayload>) { setForm(current => ({ ...current, ...patch })); setDirty(true); setSuccess('') }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (locked || protectedUser) return
    if (record && record.is_active && !form.is_active && !window.confirm('Desativar este usuário e bloquear seu acesso ao sistema?')) return
    setBusy(true); setError(''); setSuccess('')
    try {
      const saved = await saveManagedUser(record?.id ?? null, { ...form, ...(record ? {} : { password }) })
      populate(saved); setSuccess('Usuário salvo.'); setRetry(value => value + 1)
    } catch (err) {
      setError(message(err) + (!record && err instanceof ApiError && err.status === 0 ? ' Confira a lista pelo login antes de tentar criar novamente.' : ''))
    } finally { setBusy(false); setPassword('') }
  }
  async function reset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (locked || !record || protectedUser || dirty) return
    if (!window.confirm('Redefinir a senha? As sessões anteriores desse usuário perderão a validade.')) return
    setBusy(true); setError(''); setSuccess('')
    try { populate(await resetManagedUserPassword(record.id, resetPassword, record.version)); setSuccess('Senha redefinida. Informe a nova senha ao usuário por um canal seguro.') }
    catch (err) { setError(message(err)) }
    finally { setBusy(false); setResetPassword('') }
  }
  async function loadHistory() {
    if (!record || locked) return
    setBusy(true); setError('')
    try { setHistory((await getManagedUserHistory(record.id)).results) }
    catch (err) { setError(message(err)) } finally { setBusy(false) }
  }
  const filteredPermissions = options?.permissions.filter(p => `${p.name} ${p.key} ${p.section}`.toLocaleLowerCase('pt-BR').includes(permissionSearch.toLocaleLowerCase('pt-BR'))) ?? []
  const groups = [...new Set(filteredPermissions.map(p => p.section))]

  return <section className="um-page" aria-label="Gestão de usuários">
    <header className="um-heading"><div><span className="um-eyebrow">ADMINISTRAÇÃO</span><h1>Usuários e acessos</h1><p>Gerencie contas, vínculos e permissões do Lentis.</p></div>
      <button className="erp-action-button" disabled={locked || !options} onClick={newUser}>Novo usuário</button></header>
    <p className="um-notice"><strong>Gestão global do sistema.</strong> As permissões dos módulos valem nas lojas às quais a pessoa tem acesso. O perfil por loja participa das regras comerciais, mas não preenche permissões automaticamente.</p>
    {error && <div className="um-error" role="alert">{error}<button type="button" disabled={locked} onClick={() => setRetry(v => v + 1)}>Atualizar lista</button></div>}
    {success && <p className="um-success" role="status">{success}</p>}
    <div className="um-grid"><aside className="um-card um-list" aria-label="Usuários cadastrados">
      <form className="um-search" onSubmit={event => { event.preventDefault(); if (!locked && mayLeave()) { closeEditor(); setAppliedSearch(search); setPage(1); setRetry(v => v + 1) } }}>
        <label htmlFor="um-search">Buscar usuário ou nome</label><div><input id="um-search" value={search} maxLength={150} onChange={e => setSearch(e.target.value)} /><button disabled={locked}>Buscar</button></div>
      </form>
      {loading ? <p role="status">Carregando usuários…</p> : <>
        <p>{listing?.count ?? 0} usuário(s)</p>
        <ul>{listing?.results.map(u => <li key={u.id}><button className={editing && record?.id === u.id ? 'is-selected' : ''} disabled={locked} onClick={() => void openUser(u.id)}>
          <strong>{u.first_name ? `${u.first_name} ${u.last_name}`.trim() : u.username}</strong><span>@{u.username}</span><small>{u.is_active ? 'Ativo' : 'Inativo'}{u.protected ? ' · Administrador protegido' : ''}</small>
        </button></li>)}</ul>
        {listing?.count === 0 && <p>Nenhum usuário encontrado.</p>}
        <div className="um-pagination"><button disabled={locked || page === 1} onClick={() => { if (mayLeave()) { closeEditor(); setPage(p => p - 1) } }}>Anterior</button><span>Página {page}</span><button disabled={locked || !listing?.has_next} onClick={() => { if (mayLeave()) { closeEditor(); setPage(p => p + 1) } }}>Próxima</button></div>
      </>}
    </aside><div className="um-card um-editor">
      {!editing ? <div className="um-empty"><h2>Selecione um usuário</h2><p>Abra uma conta para revisar os acessos ou cadastre uma nova pessoa.</p></div> : <>
        <header><h2>{record ? `Conta de ${record.username}` : 'Novo usuário'}</h2><p>{protectedUser ? 'Administrador do sistema: conta protegida e com acesso administrativo completo. Alterações desta conta ficam no Django Admin.' : 'Preencha os dados e selecione os acessos necessários.'}</p></header>
        <form onSubmit={event => void submit(event)} autoComplete="off" aria-busy={busy}>
          <fieldset disabled={locked || protectedUser}><legend>Dados da conta</legend><div className="um-fields">
            <label>Usuário<input required maxLength={150} autoComplete="off" value={form.username} onChange={e => change({ username: e.target.value })} /></label>
            <label>E-mail<input type="email" maxLength={254} value={form.email} onChange={e => change({ email: e.target.value })} /></label>
            <label>Nome<input maxLength={150} value={form.first_name} onChange={e => change({ first_name: e.target.value })} /></label>
            <label>Sobrenome<input maxLength={150} value={form.last_name} onChange={e => change({ last_name: e.target.value })} /></label>
            {!record && <label>Senha inicial<input type="password" required minLength={8} maxLength={256} autoComplete="new-password" value={password} onChange={e => { setPassword(e.target.value); setDirty(true) }} /><small>Mínimo de 8 caracteres; os validadores do servidor também se aplicam.</small></label>}
          </div><label className="um-check"><input type="checkbox" checked={form.is_active} onChange={e => change({ is_active: e.target.checked })} />Conta ativa</label></fieldset>
          <fieldset disabled={locked || protectedUser}><legend>Vínculos com lojas</legend><p>Marque as unidades e escolha a função. Desmarcar inativa o vínculo sem apagar seu histórico.</p>
            <div className="um-stores">{options?.stores.map(store => {
              const member = form.memberships.find(m => m.store_id === store.id)
              return <div className="um-store" key={store.id}><label className="um-check"><input type="checkbox" checked={member?.is_active ?? false} disabled={!store.is_active && !member?.is_active} onChange={e => change({ memberships: [...form.memberships.filter(m => m.store_id !== store.id), { store_id: store.id, role: member?.role ?? 'seller', is_active: e.target.checked }] })} /><span>{store.code} — {store.name}{!store.is_active && ' (inativa)'}</span></label>
                <select aria-label={`Perfil em ${store.name}`} disabled={!member?.is_active || !store.is_active} value={member?.role ?? 'seller'} onChange={e => change({ memberships: form.memberships.map(m => m.store_id === store.id ? { ...m, role: e.target.value } : m) })}>{options.roles.map(role => <option key={role.value} value={role.value}>{role.label}</option>)}</select></div>
            })}</div>{!form.memberships.some(m => m.is_active) && <p className="um-notice">Sem vínculos ativos, esta conta não poderá operar nas lojas.</p>}</fieldset>
          <fieldset disabled={locked || protectedUser}><legend>Permissões dos módulos</legend>
            <p className="um-notice"><strong>Aplicação das permissões:</strong> Clientes, produtos e estoque já verificam estas permissões por ação. Outros módulos mantêm suas verificações próprias; a padronização das vendas continua na próxima etapa. Permissões não substituem os vínculos nem as regras de negócio. Para retirar todo o acesso a uma loja, desative o vínculo.</p>
            <p>Marque as concessões diretas. Permissões diretas: {form.permission_ids.length}. Herdadas de grupos: {record?.inherited_permission_ids.length ?? 0}.</p>
            {!!record?.groups.length && <p>Grupos existentes: {record.groups.join(', ')}. Gerencie grupos no Django Admin; permissões herdadas continuam efetivas mesmo com a opção direta desmarcada.</p>}
            <label>Filtrar permissões<input type="search" value={permissionSearch} onChange={e => setPermissionSearch(e.target.value)} /></label>
            <div className="um-permissions">{groups.map(group => <details key={group}><summary>{group}</summary>{filteredPermissions.filter(p => p.section === group).map(p => {
              const inherited = record?.inherited_permission_ids.includes(p.id) ?? false
              return <label className="um-check" key={p.id} data-permission-key={p.key}><input type="checkbox" checked={form.permission_ids.includes(p.id)} onChange={e => change({ permission_ids: e.target.checked ? [...form.permission_ids, p.id] : form.permission_ids.filter(id => id !== p.id) })} /><span>{p.name}{inherited && <small>Também herdada de grupo (continua efetiva)</small>}</span></label>
            })}</details>)}{!filteredPermissions.length && <p>Nenhuma permissão encontrada.</p>}</div>
          </fieldset>
          <div className="um-actions">{!protectedUser && <button className="erp-action-button" disabled={locked || (!!record && !dirty)}>{busy ? 'Aguarde…' : 'Salvar usuário'}</button>}<button type="button" disabled={locked} onClick={() => { if (mayLeave()) closeEditor() }}>Fechar cadastro</button></div>
        </form>
        {record && <section className="um-security"><h3>Segurança e histórico</h3>
          <div className="um-actions">{!protectedUser && <button disabled={locked || dirty} onClick={() => { setShowReset(v => !v); setResetPassword('') }}>Redefinir senha</button>}<button disabled={locked} onClick={() => void loadHistory()}>Carregar histórico</button></div>
          {dirty && <p>Salve ou descarte as alterações antes de redefinir a senha.</p>}
          {showReset && <form className="um-reset" onSubmit={event => void reset(event)}><label>Nova senha<input type="password" autoComplete="new-password" required minLength={8} maxLength={256} value={resetPassword} disabled={locked || dirty} onChange={e => setResetPassword(e.target.value)} /></label><button disabled={locked || dirty}>Confirmar redefinição</button></form>}
          {history && <><p>Últimos 50 registros desta funcionalidade.</p><ol className="um-history">{history.map(e => <li key={e.id}><strong>{actions[e.action] ?? e.action}</strong><span>{new Date(e.created_at).toLocaleString('pt-BR')} · {e.actor}</span><small>{Object.keys(e.changes).map(name => fields[name] ?? name).join(', ') || (e.action === 'password_reset' ? 'Credenciais não são registradas no histórico' : 'Nenhum campo alterado')}</small></li>)}</ol>{history.length === 0 && <p>Ainda não há registros desta funcionalidade.</p>}</>}
        </section>}
      </>}
    </div></div>
  </section>
}
