import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError, createCustomer, getMyCustomers, getMyStores } from '../api'
import type { AccessibleStore, CurrentUser, Customer, NewCustomer, ThemePreference } from '../api'
import ThemeSelect from './ThemeSelect'
import './AppLayout.css'
import './Customers.css'

type AppLayoutProps = {
  user: CurrentUser
  busy: boolean
  error: string
  onLogout: () => Promise<void>
  onThemeSaved: (theme: ThemePreference) => void
}

const menuGroups = [
  { title: 'Cadastros', icon: 'cadastros', items: ['Clientes', 'Produtos'] },
  { title: 'Comercial', icon: 'comercial', items: ['Vendas', 'Orçamentos', 'Caixa'] },
  { title: 'Operação', icon: 'operacao', items: ['Estoque', 'Ordens de serviço', 'Atendimento domiciliar'] },
  { title: 'Gestão', icon: 'gestao', items: ['Financeiro', 'Relatórios', 'Administração'] },
]

function MenuIcon({ name }: { name: string }) {
  const paths: Record<string, string> = {
    inicio: 'M3 10 12 3l9 7M5 9v12h5v-7h4v7h5V9',
    cadastros: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M20 8v6M17 11h6M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
    comercial: 'M3 3h2l3 12h11l2-8H6M9 20h.01M18 20h.01',
    operacao: 'M3 7 12 3l9 4v10l-9 4-9-4ZM3 7l9 4 9-4M12 11v10',
    gestao: 'M4 21V11h4v10M10 21V3h4v18M16 21V7h4v14',
    menu: 'M4 6h16M4 12h16M4 18h16',
    sair: 'M9 4H4v16h5M13 8l4 4-4 4M8 12h13',
  }
  return (
    <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={paths[name] || paths.inicio} />
    </svg>
  )
}

export default function AppLayout({ user, busy, error, onLogout, onThemeSaved }: AppLayoutProps) {
  const [collapsed, setCollapsed] = useState(false)
  const [openGroup, setOpenGroup] = useState<string | null>('Cadastros')
  const [page, setPage] = useState('Visão geral')
  const [stores, setStores] = useState<AccessibleStore[]>([])
  const [selectedStoreId, setSelectedStoreId] = useState('')
  const [loadingStores, setLoadingStores] = useState(true)
  const [storesError, setStoresError] = useState('')
  const [retry, setRetry] = useState(0)
  const [customers, setCustomers] = useState<Customer[]>([])
  const [loadingCustomers, setLoadingCustomers] = useState(false)
  const [customersError, setCustomersError] = useState('')
  const [customerSearch, setCustomerSearch] = useState('')
  const [customerFormOpen, setCustomerFormOpen] = useState(false)
  const [savingCustomer, setSavingCustomer] = useState(false)
  const [customerFormError, setCustomerFormError] = useState('')
  const [newCustomer, setNewCustomer] = useState<NewCustomer>({
    name: '', cpf: '', phone: '', email: '',
  })

  const displayName = [user.first_name, user.last_name].filter(Boolean).join(' ') || user.username
  const initials = displayName.split(/\s+/).slice(0, 2).map((part) => part[0]).join('').toUpperCase()

  useEffect(() => {
    let ignore = false
    async function loadStores() {
      try {
        const result = await getMyStores()
        if (ignore) return
        setStores(result)
        setSelectedStoreId((current) =>
          result.some((store) => String(store.id) === current)
            ? current : String(result[0]?.id ?? ''),
        )
      } catch (err) {
        if (ignore) return
        setStores([])
        setSelectedStoreId('')
        setStoresError(
          err instanceof ApiError && [401, 403].includes(err.status)
            ? 'Sua sessão não permite consultar as lojas. Saia e entre novamente.'
            : 'Não foi possível carregar suas lojas. Tente novamente.',
        )
      } finally {
        if (!ignore) setLoadingStores(false)
      }
    }
    void loadStores()
    return () => { ignore = true }
  }, [user.id, retry])

  const selectedStore = stores.find((store) => String(store.id) === selectedStoreId)
  const selectedRole = selectedStore?.role_label || 'Sem perfil'
  const filteredCustomers = customers.filter((customer) => {
    const query = customerSearch.trim().toLowerCase()
    if (!query) return true
    return [customer.name, customer.cpf || '', customer.phone, customer.email]
      .some((value) => value.toLowerCase().includes(query))
  })

  useEffect(() => {
    if (page !== 'Clientes' || !selectedStore) return
    let ignore = false
    setLoadingCustomers(true)
    setCustomersError('')
    void getMyCustomers(selectedStore.id)
      .then((result) => { if (!ignore) setCustomers(result) })
      .catch(() => { if (!ignore) setCustomersError('Não foi possível carregar os clientes.') })
      .finally(() => { if (!ignore) setLoadingCustomers(false) })
    return () => { ignore = true }
  }, [page, selectedStoreId, selectedStore?.id])

  function closeCustomerForm() {
    setCustomerFormOpen(false)
    setCustomerFormError('')
    setNewCustomer({ name: '', cpf: '', phone: '', email: '' })
  }

  async function handleCreateCustomer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedStore || savingCustomer) return
    setSavingCustomer(true)
    setCustomerFormError('')
    try {
      const created = await createCustomer(selectedStore.id, newCustomer)
      setCustomers((current) => [created, ...current])
      closeCustomerForm()
    } catch (err) {
      setCustomerFormError(err instanceof Error ? err.message : 'Não foi possível salvar o cliente.')
    } finally {
      setSavingCustomer(false)
    }
  }


  function retryStores() {
    setStoresError('')
    setLoadingStores(true)
    setRetry((value) => value + 1)
  }

  function toggleGroup(title: string) {
    if (collapsed) {
      setCollapsed(false)
      setOpenGroup(title)
      return
    }
    setOpenGroup((current) => current === title ? null : title)
  }

  return (
    <div className={`erp-layout${collapsed ? ' is-collapsed' : ''}`}>
      <aside className="erp-sidebar" aria-label="Menu principal">
        <div className="erp-brand">
          <span>{collapsed ? 'L' : 'LENTIS'}</span>
          {!collapsed && <small>ERP</small>}
        </div>
        <nav className="erp-navigation" aria-label="Módulos">
          <button type="button"
            className={`erp-nav-button${page === 'Visão geral' ? ' is-active' : ''}`}
            onClick={() => setPage('Visão geral')} aria-label="Visão geral"
            aria-current={page === 'Visão geral' ? 'page' : undefined}
            title={collapsed ? 'Visão geral' : undefined}>
            <MenuIcon name="inicio" />
            {!collapsed && <span>Visão geral</span>}
          </button>
          {!collapsed && <p className="erp-menu-label">ESPAÇO DE TRABALHO</p>}
          {menuGroups.map((group) => (
            <div className="erp-menu-group" key={group.title}>
              <button type="button" className="erp-nav-button" onClick={() => toggleGroup(group.title)}
                aria-label={group.title} aria-expanded={!collapsed && openGroup === group.title}
                aria-controls={`menu-${group.icon}`} title={collapsed ? group.title : undefined}>
                <MenuIcon name={group.icon} />
                {!collapsed && <>
                  <span>{group.title}</span>
                  <span className="erp-chevron" aria-hidden="true">{openGroup === group.title ? '−' : '+'}</span>
                </>}
              </button>
              <div id={`menu-${group.icon}`} className="erp-submenu" hidden={collapsed || openGroup !== group.title}>
                {group.items.map((item) => (
                  <button type="button" key={item} className={page === item ? 'is-active' : ''}
                    aria-current={page === item ? 'page' : undefined} onClick={() => setPage(item)}>
                    {item}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </nav>
        <div className="erp-profile">
          <div className="erp-avatar" title={displayName}>{initials}</div>
          {!collapsed && (
            <div className="erp-profile-info">
              <strong title={displayName}>{displayName}</strong>
              <span title={user.username}>@{user.username}</span>
              <span className="erp-profile-role">{selectedRole}</span>
            </div>
          )}
          <button type="button" className="erp-icon-button" onClick={() => void onLogout()}
            disabled={busy} aria-label={busy ? 'Saindo da conta' : 'Sair da conta'} title="Sair da conta">
            <MenuIcon name="sair" />
          </button>
        </div>
      </aside>

      <div className="erp-workspace">
        <header className="erp-topbar">
          <div className="erp-topbar-heading">
            <button type="button" className="erp-icon-button" onClick={() => setCollapsed((value) => !value)}
              aria-label={collapsed ? 'Expandir menu' : 'Recolher menu'} aria-expanded={!collapsed}>
              <MenuIcon name="menu" />
            </button>
            <span>{page}</span>
          </div>
          <ThemeSelect value={user.theme} disabled={busy} onSaved={onThemeSaved} />
          <div className="erp-store-field">
            <label htmlFor="active-store">Unidade</label>
            <select id="active-store" value={selectedStoreId}
              onChange={(event) => setSelectedStoreId(event.target.value)}
              disabled={loadingStores || !!storesError || stores.length === 0}>
              {loadingStores ? <option value="">Carregando…</option>
                : storesError ? <option value="">Indisponível</option>
                : stores.length === 0 ? <option value="">Sem unidades</option>
                : stores.map((store) => (
                  <option key={store.id} value={String(store.id)}>{store.code} — {store.name}</option>
                ))}
            </select>
          </div>
        </header>

        <main className="erp-content">
          {error && <p className="erp-alert" role="alert">{error}</p>}
          {loadingStores ? (
            <div className="erp-card" role="status">Carregando suas unidades…</div>
          ) : storesError ? (
            <div className="erp-card">
              <p className="erp-alert" role="alert">{storesError}</p>
              <button className="erp-action-button" type="button" onClick={retryStores}>Tentar novamente</button>
            </div>
          ) : !selectedStore ? (
            <section className="erp-card">
              <h1>Nenhuma unidade disponível</h1>
              <p>Você ainda não possui acesso a uma unidade ativa. Solicite a liberação ao administrador.</p>
            </section>
          ) : page === 'Clientes' ? (
            <section className="erp-clientes-page">
              <div className="erp-page-heading erp-list-heading">
                <div>
                  <span className="erp-kicker">CADASTROS</span>
                  <h1>Clientes</h1>
                  <p>Clientes cadastrados em {selectedStore.name}.</p>
                </div>
                <button className="erp-action-button" type="button"
                  onClick={() => { setCustomerFormError(''); setCustomerFormOpen(true) }}>
                  Novo cliente
                </button>
              </div>
              {customerFormOpen && (
                <form className="erp-card erp-customer-form" onSubmit={(event) => void handleCreateCustomer(event)}>
                  <div className="erp-form-heading">
                    <div><span className="erp-card-label">NOVO CADASTRO</span><h2>Adicionar cliente</h2></div>
                    <button type="button" className="erp-secondary-button" onClick={closeCustomerForm}>Cancelar</button>
                  </div>
                  <div className="erp-form-grid">
                    <label>Nome completo<input required value={newCustomer.name} onChange={(event) => setNewCustomer({ ...newCustomer, name: event.target.value })} /></label>
                    <label>CPF<input placeholder="000.000.000-00" value={newCustomer.cpf} onChange={(event) => setNewCustomer({ ...newCustomer, cpf: event.target.value })} /></label>
                    <label>Telefone<input value={newCustomer.phone} onChange={(event) => setNewCustomer({ ...newCustomer, phone: event.target.value })} /></label>
                    <label>E-mail<input type="email" value={newCustomer.email} onChange={(event) => setNewCustomer({ ...newCustomer, email: event.target.value })} /></label>
                  </div>
                  {customerFormError && <p className="erp-alert" role="alert">{customerFormError}</p>}
                  <button className="erp-action-button" type="submit" disabled={savingCustomer}>{savingCustomer ? 'Salvando…' : 'Salvar cliente'}</button>
                </form>
              )}
              <div className="erp-card erp-customer-list-card">
                <div className="erp-list-toolbar">
                  <input aria-label="Buscar clientes" placeholder="Buscar por nome, CPF, telefone ou e-mail" value={customerSearch} onChange={(event) => setCustomerSearch(event.target.value)} />
                  <span className="erp-card-label">{filteredCustomers.length} cliente{filteredCustomers.length === 1 ? '' : 's'}</span>
                </div>
                {loadingCustomers ? <p role="status">Carregando clientes…</p>
                  : customersError ? <p className="erp-alert" role="alert">{customersError}</p>
                  : filteredCustomers.length === 0 ? <p>Nenhum cliente encontrado nesta unidade.</p>
                  : <div className="erp-customer-table-wrap"><table className="erp-customer-table"><thead><tr><th>Nome</th><th>CPF</th><th>Telefone</th><th>E-mail</th></tr></thead><tbody>{filteredCustomers.map((customer) => <tr key={customer.id}><td>{customer.name}</td><td>{customer.cpf || '—'}</td><td>{customer.phone || '—'}</td><td>{customer.email || '—'}</td></tr>)}</tbody></table></div>}
              </div>
            </section>
          ) : page === 'Visão geral' ? (
            <>
              <div className="erp-page-heading">
                <span className="erp-kicker">VISÃO GERAL</span>
                <h1>Olá, {user.first_name || user.username}!</h1>
                <p>Seu espaço de trabalho na unidade {selectedStore.name}.</p>
              </div>
              <div className="erp-summary-grid">
                <section className="erp-card">
                  <span className="erp-card-label">Unidade selecionada</span>
                  <h2>{selectedStore.name}</h2>
                  <p>Código {selectedStore.code}</p>
                  <p className="erp-store-role">Perfil: {selectedRole}</p>
                </section>
                <section className="erp-card">
                  <span className="erp-card-label">Seu acesso</span>
                  <h2>{stores.length} {stores.length === 1 ? 'unidade' : 'unidades'}</h2>
                  <p>Disponíveis para sua conta.</p>
                </section>
              </div>
              <section className="erp-card erp-welcome-card">
                <span className="erp-development-badge">Em construção</span>
                <h2>O dia a dia da sua ótica, em um só lugar.</h2>
                <p>Os indicadores de vendas, estoque e financeiro aparecerão aqui conforme os módulos forem implementados.</p>
              </section>
            </>
          ) : (
            <section className="erp-card">
              <span className="erp-development-badge">Em desenvolvimento</span>
              <h1>{page}</h1>
              <p>Este módulo ainda não está disponível. A unidade selecionada é {selectedStore.name}.</p>
            </section>
          )}
        </main>
      </div>
    </div>
  )
}
