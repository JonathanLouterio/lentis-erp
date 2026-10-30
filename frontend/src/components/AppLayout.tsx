import FormDialog from './FormDialog'
import { useInsightAccess } from '../hooks/useInsightAccess'
import { useSupplierAccess } from '../hooks/useSupplierAccess'
import { useClinicalAccess } from '../hooks/useClinicalAccess'
import { usePurchaseAccess } from '../hooks/usePurchaseAccess'
import { useOrderAccess } from '../hooks/useOrderAccess'
import { useQuoteAccess } from '../hooks/useQuoteAccess'
import { useFinanceAccess } from '../hooks/useFinanceAccess'
import { getSaleAccess } from '../api'
import type { SaleAccess } from '../api'
import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError, createCustomer, createProduct, deleteCustomer, deleteProduct, getMyCustomers, getMyProducts, getMyStores, updateCustomer, updateProduct } from '../api'
import type { AccessibleStore, CurrentUser, Customer, CustomerPayload, Product, ProductPayload, ThemePreference } from '../api'
import ThemeSelect from './ThemeSelect'
import StockMovements from './StockMovements'
import Sales from './Sales'
import Receivables from './Receivables'
import CashRegister from './CashRegister'
import Dashboard from './Dashboard'
import Quotes from './Quotes'
import Prescriptions from './Prescriptions'
import ServiceOrders from './ServiceOrders'
import CustomerHistory from './CustomerHistory'
import Suppliers from './Suppliers'
import Purchases from './Purchases'
import Payables from './Payables'
import Reports from './Reports'
import UserManagement from './UserManagement'
import { getUserManagementOptions, getCatalogAccess } from '../api'
import type { CatalogAccess } from '../api'
import type { DashboardAction } from './Dashboard'
import './AppLayout.css'
import './Customers.css'
import './WorkspaceVisual.css'
import './MobileWorkspace.css'

type AppLayoutProps = {
  user: CurrentUser
  busy: boolean
  error: string
  onLogout: () => Promise<void>
  onThemeSaved: (theme: ThemePreference) => void
}

const menuGroups = [
  { title: 'Cadastros', icon: 'cadastros', items: ['Clientes', 'Produtos', 'Receitas', 'Fornecedores'] },
  { title: 'Comercial', icon: 'comercial', items: ['Vendas', 'Orçamentos', 'Compras', 'Caixa'] },
  { title: 'Operação', icon: 'operacao', items: ['Estoque', 'Ordens de serviço', 'Atendimento domiciliar'] },
  { title: 'Gestão', icon: 'gestao', items: ['Financeiro', 'Contas a pagar', 'Relatórios', 'Usuários e acessos'] },
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
  const [canManageUsers, setCanManageUsers] = useState(false)
  useEffect(() => {
    let ignore = false
    void getUserManagementOptions().then(() => { if (!ignore) setCanManageUsers(true) }).catch(() => { if (!ignore) setCanManageUsers(false) })
    return () => { ignore = true }
  }, [])
  const [mobile, setMobile] = useState(() => window.matchMedia('(max-width: 900px)').matches)
  const [desktopCollapsed, setCollapsed] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const menuDialog = useRef<HTMLDialogElement>(null)
  const collapsed = mobile ? false : desktopCollapsed
  useEffect(() => {
    const media = window.matchMedia('(max-width: 900px)')
    const onChange = () => { setMobile(media.matches); setMenuOpen(false) }
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [])
  useEffect(() => {
    const dialog = menuDialog.current
    if (!dialog) return
    if (menuOpen && mobile) { if (!dialog.open) dialog.showModal() }
    else if (dialog.open) dialog.close()
    return () => { if (dialog.open) dialog.close() }
  }, [menuOpen, mobile])
  const [openGroup, setOpenGroup] = useState<string | null>('Cadastros')
  const [page, setPage] = useState('Visão geral')
  useEffect(() => {
    setMenuOpen(false)
  }, [page])
  const [payablePurchaseId, setPayablePurchaseId] = useState<number | undefined>(undefined)
  const [historyCustomerId, setHistoryCustomerId] = useState<number | null>(null)
  const [orderSaleId, setOrderSaleId] = useState<number | undefined>(undefined)
  const [salesStartNew, setSalesStartNew] = useState(false)
  const [dashboardSaleId, setDashboardSaleId] = useState<number | undefined>(undefined)
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
  const [customerDirty, setCustomerDirty] = useState(false)
  const [savingCustomer, setSavingCustomer] = useState(false)
  const [customerFormError, setCustomerFormError] = useState('')
  const [editingCustomer, setEditingCustomer] = useState<Customer | null>(null)
  const emptyCustomer = (): CustomerPayload => ({
    person_type: 'individual', name: '', trade_name: '', cpf: '', cnpj: '', rg: '',
    state_registration: '', birth_date: '', phone: '', whatsapp: '', email: '',
    zip_code: '', street: '', address_number: '', address_complement: '',
    neighborhood: '', city: '', state: '', notes: '',
  })
  const [customerForm, setCustomerForm] = useState<CustomerPayload>(emptyCustomer)
  const [products, setProducts] = useState<Product[]>([])
  const [loadingProducts, setLoadingProducts] = useState(false)
  const [productsError, setProductsError] = useState('')
  const [productSearch, setProductSearch] = useState('')
  const [productFormOpen, setProductFormOpen] = useState(false)
  const [productDirty, setProductDirty] = useState(false)
  const [savingProduct, setSavingProduct] = useState(false)
  const [productFormError, setProductFormError] = useState('')
  const [editingProduct, setEditingProduct] = useState<Product | null>(null)
  const [savingStock, setSavingStock] = useState(false)
  const [savingSale, setSavingSale] = useState(false)
  const [saleDirty, setSaleDirty] = useState(false)
  const [stockProductId, setStockProductId] = useState('')
  const workspaceBusy = busy || savingCustomer || savingProduct || savingStock || savingSale
  const emptyProduct = (): ProductPayload => ({
    internal_code: '', barcode: '', name: '', brand: '', category: '',
    cost_price: '0', sale_price: '0', minimum_stock: '0',
  })
  const [productForm, setProductForm] = useState<ProductPayload>(emptyProduct)

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

  const [catalogAccess, setCatalogAccess] = useState<CatalogAccess | null>(null)
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [catalogError, setCatalogError] = useState('')
  const [catalogRetry, setCatalogRetry] = useState(0)
  const selectedStore = stores.find((store) => String(store.id) === selectedStoreId)
  const selectedRole = selectedStore?.role_label || 'Sem perfil'
  const access = catalogAccess?.store_id === selectedStore?.id ? catalogAccess : null
  useEffect(() => {
    if (!selectedStore) { setCatalogAccess(null); setCatalogLoading(false); return }
    let ignore = false
    setCatalogLoading(true); setCatalogError('')
    void getCatalogAccess(selectedStore.id).then(result => {
      if (!ignore) setCatalogAccess(result)
    }).catch(err => {
      if (!ignore) { setCatalogAccess(null); setCatalogError(err instanceof Error ? err.message : 'Não foi possível conferir seus acessos.') }
    }).finally(() => { if (!ignore) setCatalogLoading(false) })
    return () => { ignore = true }
  }, [selectedStore?.id, page, catalogRetry])
  useEffect(() => {
    const refresh = () => setCatalogRetry(value => value + 1)
    window.addEventListener('focus', refresh)
    return () => window.removeEventListener('focus', refresh)
  }, [])
  function refreshAccessOnDenial(err: unknown) {
    if (err instanceof ApiError && err.status === 403) setCatalogRetry(value => value + 1)
  }
  const [saleAccess, setSaleAccess] = useState<SaleAccess | null>(null)
  useEffect(() => {
    if (!selectedStore) { setSaleAccess(null); return }
    let ignore = false
    void getSaleAccess(selectedStore.id).then(next => { if (!ignore) setSaleAccess(next) })
      .catch(() => { if (!ignore) setSaleAccess(null) })
    return () => { ignore = true }
  }, [selectedStore?.id, page, catalogRetry])
  const financeRights=useFinanceAccess(selectedStore?.id ?? 0,catalogRetry)
  const insightRights=useInsightAccess(selectedStore?.id ?? 0,catalogRetry)
  const supplierRights=useSupplierAccess(selectedStore?.id ?? 0,catalogRetry)
  const clinicalRights=useClinicalAccess(selectedStore?.id ?? 0,catalogRetry)
  const purchaseRights=usePurchaseAccess(selectedStore?.id ?? 0,catalogRetry)
  const orderRights=useOrderAccess(selectedStore?.id ?? 0,catalogRetry)
  const quoteRights=useQuoteAccess(selectedStore?.id ?? 0,catalogRetry)
  function catalogMenuVisible(item: string) {
    if(item==='Fornecedores')return !!supplierRights.access?.actions.view
    if(item==='Relatórios')return Object.values(insightRights.access?.reports||{}).some(Boolean)
    if(item==='Receitas')return !!clinicalRights.access?.prescriptions.view
    if(item==='Histórico do cliente')return !!clinicalRights.access?.history
    if(item==='Compras')return !!purchaseRights.access?.purchases.view
    if(item==='Contas a pagar')return !!purchaseRights.access?.payables.view
    if(item==='Ordens de serviço')return !!orderRights.access?.actions.view
    if(item==='Orçamentos')return !!quoteRights.access && Object.values(quoteRights.access.actions).some(Boolean)
    if(item==='Caixa')return !!financeRights.access && Object.values(financeRights.access.cash).some(Boolean)
    if(item==='Financeiro')return !!financeRights.access && (financeRights.access.receipts.view || financeRights.access.receipts.receive)
    if (item === 'Vendas') return !!saleAccess && saleAccess.store_id === selectedStore?.id && Object.entries(saleAccess).some(([key,value]) => key !== 'store_id' && value === true)
    if (!access || catalogError) return !['Clientes', 'Produtos', 'Estoque'].includes(item)
    if (item === 'Clientes') return Object.values(access.customers).some(Boolean)
    if (item === 'Produtos') return Object.values(access.products).some(Boolean)
    if (item === 'Estoque') return access.stock.view || access.stock.add
    return true
  }
  const filteredCustomers = customers.filter((customer) => {
    const query = customerSearch.trim().toLowerCase()
    if (!query) return true
    return [customer.name, customer.trade_name, customer.cpf || '', customer.cnpj || '', customer.phone, customer.email]
      .some((value) => value.toLowerCase().includes(query))
  })
  const filteredProducts = products.filter((product) => {
    const query = productSearch.trim().toLowerCase()
    if (!query) return true
    return [product.internal_code, product.barcode, product.name, product.brand, product.category]
      .some((value) => value.toLowerCase().includes(query))
  })

  useEffect(() => {
    if (page !== 'Clientes' || !selectedStore || !access?.customers.view) { if (page === 'Clientes') setCustomers([]); return }
    let ignore = false
    setLoadingCustomers(true)
    setCustomersError('')
    void getMyCustomers(selectedStore.id)
      .then((result) => { if (!ignore) setCustomers(result) })
      .catch(err => { if (!ignore) { setCustomers([]); setCustomersError(err instanceof Error ? err.message : 'Não foi possível carregar os clientes.'); refreshAccessOnDenial(err) } })
      .finally(() => { if (!ignore) setLoadingCustomers(false) })
    return () => { ignore = true }
  }, [page, selectedStoreId, selectedStore?.id, access?.customers.view])

  useEffect(() => {
    if (page !== 'Produtos' || !selectedStore || !access?.products.view) { if (page === 'Produtos') setProducts([]); return }
    let ignore = false
    setLoadingProducts(true)
    setProductsError('')
    void getMyProducts(selectedStore.id)
      .then((result) => { if (!ignore) setProducts(result) })
      .catch((err) => { if (!ignore) { setProducts([]); setProductsError(err instanceof Error ? err.message : 'Não foi possível carregar os produtos.'); refreshAccessOnDenial(err) } })
      .finally(() => { if (!ignore) setLoadingProducts(false) })
    return () => { ignore = true }
  }, [page, selectedStoreId, selectedStore?.id, access?.products.view])

  function closeCustomerForm() {
    setCustomerFormOpen(false)
    setCustomerDirty(false)
    setCustomerFormError('')
    setEditingCustomer(null)
    setCustomerForm(emptyCustomer())
  }

  function openNewCustomer() {
    if (!access?.customers.add || catalogLoading) return
    setEditingCustomer(null)
    setCustomerForm(emptyCustomer())
    setCustomerFormError('')
    setCustomerFormOpen(true)
    setCustomerDirty(false)
  }

  function openEditCustomer(customer: Customer) {
    if (!access?.customers.change || catalogLoading) return
    setEditingCustomer(customer)
    setCustomerForm({
      person_type: customer.person_type, name: customer.name, trade_name: customer.trade_name || '',
      cpf: customer.cpf || '', cnpj: customer.cnpj || '', rg: customer.rg || '',
      state_registration: customer.state_registration || '', birth_date: customer.birth_date || '',
      phone: customer.phone || '', whatsapp: customer.whatsapp || '', email: customer.email || '',
      zip_code: customer.zip_code || '', street: customer.street || '', address_number: customer.address_number || '',
      address_complement: customer.address_complement || '', neighborhood: customer.neighborhood || '',
      city: customer.city || '', state: customer.state || '', notes: customer.notes || '',
    })
    setCustomerFormError('')
    setCustomerFormOpen(true)
    setCustomerDirty(false)
  }

  async function handleSaveCustomer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedStore || savingCustomer) return
    if (!(editingCustomer ? access?.customers.change : access?.customers.add)) { setCustomerFormError('Seu usuário não tem permissão para salvar este cadastro.'); return }
    setSavingCustomer(true)
    setCustomerFormError('')
    try {
      const saved = editingCustomer
        ? await updateCustomer(selectedStore.id, editingCustomer.id, customerForm)
        : await createCustomer(selectedStore.id, customerForm)
      setCustomers((current) => editingCustomer
        ? current.map((item) => item.id === saved.id ? saved : item)
        : [saved, ...current])
      closeCustomerForm()
    } catch (err) {
      refreshAccessOnDenial(err)
      setCustomerFormError(err instanceof Error ? err.message : 'Não foi possível salvar o cliente.')
    } finally {
      setSavingCustomer(false)
    }
  }

  async function handleDeleteCustomer(customer: Customer) {
    if (!selectedStore || savingCustomer) return
    if (!access?.customers.delete) { setCustomersError('Seu usuário não tem permissão para inativar este cadastro.'); return }
    if (!window.confirm(`Inativar o cliente "${customer.name}"?`)) return
    setSavingCustomer(true)
    setCustomersError('')
    try {
      await deleteCustomer(selectedStore.id, customer.id)
      setCustomers((current) => current.filter((item) => item.id !== customer.id))
    } catch (err) {
      refreshAccessOnDenial(err)
      setCustomersError(err instanceof Error ? err.message : 'Não foi possível inativar o cliente.')
    } finally {
      setSavingCustomer(false)
    }
  }

  function closeProductForm() {
    setProductFormOpen(false)
    setProductDirty(false)
    setProductFormError('')
    setEditingProduct(null)
    setProductForm(emptyProduct())
  }

  function openNewProduct() {
    if (!access?.products.add || catalogLoading) return
    setEditingProduct(null)
    setProductForm(emptyProduct())
    setProductFormError('')
    setProductFormOpen(true)
    setProductDirty(false)
  }

  function openEditProduct(product: Product) {
    if (!access?.products.change || catalogLoading) return
    setEditingProduct(product)
    setProductForm({
      internal_code: product.internal_code, barcode: product.barcode || '', name: product.name,
      brand: product.brand || '', category: product.category || '', cost_price: product.cost_price,
      sale_price: product.sale_price, minimum_stock: product.minimum_stock,
    })
    setProductFormError('')
    setProductFormOpen(true)
    setProductDirty(false)
  }

  async function handleSaveProduct(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedStore || savingProduct) return
    if (!(editingProduct ? access?.products.change : access?.products.add)) { setProductFormError('Seu usuário não tem permissão para salvar este cadastro.'); return }
    setSavingProduct(true)
    setProductFormError('')
    try {
      const saved = editingProduct
        ? await updateProduct(selectedStore.id, editingProduct.id, productForm)
        : await createProduct(selectedStore.id, productForm)
      setProducts((current) => editingProduct
        ? current.map((item) => item.id === saved.id ? saved : item)
        : [saved, ...current])
      closeProductForm()
    } catch (err) {
      refreshAccessOnDenial(err)
      setProductFormError(err instanceof Error ? err.message : 'Não foi possível salvar o produto.')
    } finally {
      setSavingProduct(false)
    }
  }

  async function handleDeleteProduct(product: Product) {
    if (!selectedStore || savingProduct) return
    if (!access?.products.delete) { setProductsError('Seu usuário não tem permissão para inativar este cadastro.'); return }
    if (!window.confirm(`Inativar o produto "${product.name}"?`)) return
    setSavingProduct(true)
    setProductsError('')
    try {
      await deleteProduct(selectedStore.id, product.id)
      setProducts((current) => current.filter((item) => item.id !== product.id))
    } catch (err) {
      refreshAccessOnDenial(err)
      setProductsError(err instanceof Error ? err.message : 'Não foi possível inativar o produto.')
    } finally {
      setSavingProduct(false)
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

  function openStock(productId = '') {
    setMenuOpen(false)
    setStockProductId(productId)
    setOpenGroup('Operação')
    setPage('Estoque')
  }

  function leaveSaleAllowed() {
    return !['Vendas', 'Financeiro', 'Caixa', 'Orçamentos', 'Receitas', 'Ordens de serviço', 'Fornecedores', 'Compras', 'Contas a pagar', 'Usuários e acessos'].includes(page) || !saleDirty || window.confirm('Sair deste atendimento? Alterações não salvas serão descartadas. Um envio pendente poderá ser conferido ao retornar.')
  }

  function changePage(nextPage: string) {
    if (nextPage === page) { setMenuOpen(false); return }
    if (!leaveSaleAllowed()) return
    setMenuOpen(false)
    if (nextPage === 'Contas a pagar') setPayablePurchaseId(undefined)
    if (nextPage === 'Vendas') { setSalesStartNew(false); setDashboardSaleId(undefined) }
    if (nextPage === 'Ordens de serviço') setOrderSaleId(undefined)
    setPage(nextPage)
  }

  function dashboardAction(action: DashboardAction, id?: number) {
    if (action === 'stock') { openStock(id ? String(id) : ''); return }
    if (action === 'new-customer') { setOpenGroup('Cadastros'); setPage('Clientes'); openNewCustomer(); return }
    if (action === 'receivables') { setOpenGroup('Gestão'); changePage('Financeiro'); return }
    setOpenGroup('Comercial')
    if (action === 'cash') { changePage('Caixa'); return }
    setSalesStartNew(action === 'new-sale'); setDashboardSaleId(action === 'sale' ? id : undefined); setPage('Vendas')
  }

  function changeStore(storeId: string) {
    if (!leaveSaleAllowed()) return
    closeCustomerForm()
    closeProductForm()
    setCustomers([])
    setProducts([])
    setStockProductId('')
    setSalesStartNew(false); setDashboardSaleId(undefined)
    setPayablePurchaseId(undefined)
    setSelectedStoreId(storeId)
  }

  const sidebar = (
      <aside id="erp-navigation-panel" className="erp-sidebar" aria-label="Menu principal">
        <div className="erp-brand">
          <span>{collapsed ? 'L' : 'LENTIS'}</span>
          {!collapsed && <small>ERP</small>}
        </div>
        {mobile && <button type="button" className="erp-mobile-menu-close" onClick={() => setMenuOpen(false)} aria-label="Fechar menu">Fechar menu ×</button>}
        <nav className="erp-navigation" aria-label="Módulos">
          <button type="button" disabled={workspaceBusy}
            className={`erp-nav-button${page === 'Visão geral' ? ' is-active' : ''}`}
            onClick={() => changePage('Visão geral')} aria-label="Visão geral"
            aria-current={page === 'Visão geral' ? 'page' : undefined}
            title={collapsed ? 'Visão geral' : undefined}>
            <MenuIcon name="inicio" />
            {!collapsed && <span>Visão geral</span>}
          </button>
          {!collapsed && <p className="erp-menu-label">ESPAÇO DE TRABALHO</p>}
          {menuGroups.map((group) => (
            <div className="erp-menu-group" key={group.title}>
              <button type="button" disabled={workspaceBusy} className="erp-nav-button" onClick={() => toggleGroup(group.title)}
                aria-label={group.title} aria-expanded={!collapsed && openGroup === group.title}
                aria-controls={`menu-${group.icon}`} title={collapsed ? group.title : undefined}>
                <MenuIcon name={group.icon} />
                {!collapsed && <>
                  <span>{group.title}</span>
                  <span className="erp-chevron" aria-hidden="true">{openGroup === group.title ? '−' : '+'}</span>
                </>}
              </button>
              <div id={`menu-${group.icon}`} className="erp-submenu" hidden={collapsed || openGroup !== group.title}>
                {group.items.filter(item => (item !== 'Usuários e acessos' || canManageUsers) && catalogMenuVisible(item)).map((item) => (
                  <button type="button" disabled={workspaceBusy} key={item} className={page === item ? 'is-active' : ''}
                    aria-current={page === item ? 'page' : undefined} onClick={() => {
                      if (item === 'Estoque') { if (leaveSaleAllowed()) openStock() }
                      else changePage(item)
                    }}>
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
          <button type="button" className="erp-icon-button" onClick={() => { if (leaveSaleAllowed()) void onLogout() }}
            disabled={workspaceBusy} aria-label={busy ? 'Saindo da conta' : 'Sair da conta'} title="Sair da conta">
            <MenuIcon name="sair" />
          </button>
        </div>
      </aside>
  )

  return (
    <div className={`erp-layout${collapsed ? ' is-collapsed' : ''}${mobile ? ' is-mobile' : ''}`}>
      {mobile ? <dialog ref={menuDialog} className="erp-mobile-menu" aria-label="Menu principal"
        onCancel={event => { event.preventDefault(); setMenuOpen(false) }}
        onClose={() => setMenuOpen(false)}
        onKeyDown={event => {
          if (event.key !== 'Tab') return
          const buttons = [...event.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')]
            .filter(button => button.getClientRects().length > 0)
          const first = buttons[0], last = buttons[buttons.length - 1]
          if (!first) { event.preventDefault(); return }
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
        }}
        onClick={event => { if (event.target === event.currentTarget) setMenuOpen(false) }}>
        {sidebar}
      </dialog> : sidebar}

      <div className="erp-workspace">
        <header className="erp-topbar">
          <div className="erp-topbar-heading">
            <button type="button" className="erp-icon-button" onClick={() => mobile ? setMenuOpen(true) : setCollapsed(value => !value)}
              aria-label={mobile ? 'Abrir menu' : collapsed ? 'Expandir menu' : 'Recolher menu'}
              aria-controls="erp-navigation-panel" aria-expanded={mobile ? menuOpen : !collapsed}>
              <MenuIcon name="menu" />
            </button>
            <span>{page}</span>
          </div>
          <ThemeSelect value={user.theme} disabled={workspaceBusy} onSaved={onThemeSaved} />
          <div className="erp-store-field">
            <label htmlFor="active-store">Unidade</label>
            <select id="active-store" value={selectedStoreId}
              onChange={(event) => changeStore(event.target.value)}
              disabled={workspaceBusy || loadingStores || !!storesError || stores.length === 0}>
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
          {page === 'Usuários e acessos' && canManageUsers ? (
            <UserManagement onSavingChange={setSavingSale} onDirtyChange={setSaleDirty} />
          ) : loadingStores ? (
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
          ) : ['Clientes', 'Produtos', 'Estoque'].includes(page) && (catalogError || !access) ? (
            <section className="erp-card" role={catalogError ? 'alert' : 'status'}>
              <p>{catalogError || 'Conferindo suas permissões…'}</p>
              {!catalogLoading && <button type="button" className="erp-action-button" onClick={() => setCatalogRetry(value => value + 1)}>Atualizar acessos</button>}
            </section>
          ) : !catalogMenuVisible(page) ? (
            <section className="erp-card"><h1>Acesso não permitido</h1><p>Solicite ao administrador as permissões para este módulo nesta unidade.</p><button type="button" className="erp-action-button" onClick={() => setCatalogRetry(value => value + 1)}>Atualizar acessos</button></section>
          ) : page === 'Vendas' ? (
            <Sales key={`${selectedStore.id}.${dashboardSaleId ?? (salesStartNew ? 'new' : 'list')}`} startNew={salesStartNew} initialSaleId={dashboardSaleId} onServiceOrder={orderRights.access?.actions.view ? (id) => { if (!leaveSaleAllowed()) return; setOrderSaleId(id); setPage('Ordens de serviço'); setOpenGroup('Operação') } : undefined} store={selectedStore} userId={user.id} onSavingChange={setSavingSale} onDirtyChange={setSaleDirty} />
          ) : page === 'Ordens de serviço' ? (
            <ServiceOrders initialSaleId={orderSaleId} key={`${selectedStore.id}.${orderSaleId ?? "list"}`} store={selectedStore} userId={user.id} onSavingChange={setSavingSale} onDirtyChange={setSaleDirty} />
          ) : page === 'Receitas' ? (
            <Prescriptions key={selectedStore.id} store={selectedStore} userId={user.id} onSavingChange={setSavingSale} onDirtyChange={setSaleDirty} />
          ) : page === 'Orçamentos' ? (
            <Quotes key={selectedStore.id} store={selectedStore} userId={user.id} onSavingChange={setSavingSale} onDirtyChange={setSaleDirty} onOpenSale={id => dashboardAction('sale', id)} />
          ) : page === 'Caixa' ? (
            <CashRegister key={selectedStore.id} store={selectedStore} userId={user.id} onSavingChange={setSavingSale} onDirtyChange={setSaleDirty} />
          ) : page === 'Financeiro' ? (
            <Receivables key={selectedStore.id} store={selectedStore} userId={user.id} onSavingChange={setSavingSale} onDirtyChange={setSaleDirty} />
          ) : page === 'Estoque' ? (
            <StockMovements key={selectedStore.id} store={selectedStore}
              initialProductId={stockProductId} permissions={access?.stock ?? { view: false, add: false }} onSavingChange={setSavingStock} />
          ) : page === 'Produtos' ? (
            <section className="erp-clientes-page">
              <div className="erp-page-heading erp-list-heading">
                <div>
                  <span className="erp-kicker">CADASTROS</span>
                  <h1>Produtos</h1>
                  <p>Produtos cadastrados em {selectedStore.name}.</p>
                </div>
                {access?.products.add && <button className="erp-action-button" type="button" disabled={workspaceBusy || catalogLoading} onClick={openNewProduct}>Novo produto</button>}
              </div>
              {productFormOpen && (editingProduct ? access?.products.change : access?.products.add) && (
                <FormDialog title={editingProduct ? 'Editar produto' : 'Novo produto'} subtitle={selectedStore.name} busy={savingProduct} dirty={productDirty} onClose={closeProductForm} actions={<button className="erp-action-button" type="submit" form="lentis-product-form" disabled={savingProduct}>{savingProduct ? 'Salvando…' : editingProduct ? 'Salvar alterações' : 'Salvar produto'}</button>}>
                <form id="lentis-product-form" onChangeCapture={() => setProductDirty(true)} className="erp-card erp-customer-form" onSubmit={(event) => void handleSaveProduct(event)}>
                  <fieldset className="erp-window-fields" disabled={savingProduct}>
                  <div className="erp-form-grid">
                    <label>Código interno<input required value={productForm.internal_code} onChange={(event) => setProductForm({ ...productForm, internal_code: event.target.value })} /></label>
                    <label>Código de barras<input value={productForm.barcode} onChange={(event) => setProductForm({ ...productForm, barcode: event.target.value })} /></label>
                    <label className="erp-field-wide">Descrição<input required value={productForm.name} onChange={(event) => setProductForm({ ...productForm, name: event.target.value })} /></label>
                    <label>Marca<input value={productForm.brand} onChange={(event) => setProductForm({ ...productForm, brand: event.target.value })} /></label>
                    <label>Categoria<input value={productForm.category} onChange={(event) => setProductForm({ ...productForm, category: event.target.value })} /></label>
                    <label>Preço de custo<input type="number" min="0" step="0.01" value={productForm.cost_price} onChange={(event) => setProductForm({ ...productForm, cost_price: event.target.value })} /></label>
                    <label>Preço de venda<input type="number" min="0" step="0.01" value={productForm.sale_price} onChange={(event) => setProductForm({ ...productForm, sale_price: event.target.value })} /></label>
                    <label>Estoque atual<input readOnly value={editingProduct?.stock_quantity ?? '0.000'} /><small>Saldo atualizado pelas movimentações de estoque.</small></label>
                    <label>Estoque mínimo<input type="number" min="0" step="0.001" value={productForm.minimum_stock} onChange={(event) => setProductForm({ ...productForm, minimum_stock: event.target.value })} /></label>
                  </div>
                  {productFormError && <p className="erp-alert" role="alert">{productFormError}</p>}

                  </fieldset>
                </form>
                </FormDialog>
              )}
              {access?.products.view ? <div className="erp-card erp-customer-list-card">
                <div className="erp-list-toolbar">
                  <input aria-label="Buscar produtos" placeholder="Buscar por código, nome, marca ou código de barras" value={productSearch} onChange={(event) => setProductSearch(event.target.value)} />
                  <span className="erp-card-label">{filteredProducts.length} produto{filteredProducts.length === 1 ? '' : 's'}</span>
                </div>
                {loadingProducts ? <p role="status">Carregando produtos…</p>
                  : productsError ? <p className="erp-alert" role="alert">{productsError}</p>
                  : filteredProducts.length === 0 ? <p>Nenhum produto encontrado nesta unidade.</p>
                  : <div className="erp-customer-table-wrap"><table className="erp-customer-table"><thead><tr><th>Código</th><th>Produto</th><th>Categoria</th><th>Venda</th><th>Estoque</th><th>Ações</th></tr></thead><tbody>{filteredProducts.map((product) => <tr key={product.id}><td>{product.internal_code}</td><td>{product.name}</td><td>{product.category || '—'}</td><td>R$ {Number(product.sale_price).toFixed(2)}</td><td>{product.stock_quantity}</td><td className="erp-customer-actions">{access?.products.change && <button type="button" disabled={workspaceBusy} className="erp-table-button" onClick={() => openEditProduct(product)}>Editar</button>}{(access?.stock.view || access?.stock.add) && <button type="button" disabled={workspaceBusy} className="erp-table-button" onClick={() => openStock(String(product.id))}>Estoque</button>}{access?.products.delete && <button type="button" disabled={workspaceBusy} className="erp-table-button is-danger" onClick={() => void handleDeleteProduct(product)}>Inativar</button>}</td></tr>)}</tbody></table></div>}
              </div> : <div className="erp-card"><p>Você não tem permissão para consultar a lista de produtos. O cadastro de novos registros depende da permissão de cadastrar.</p></div>}
            </section>
          ) : page === 'Histórico do cliente' && historyCustomerId ? (
            <CustomerHistory key={`${selectedStore.id}.${historyCustomerId}`} store={selectedStore} customerId={historyCustomerId} onBack={() => setPage('Clientes')} onSale={(id) => { setSalesStartNew(false); setDashboardSaleId(id); setPage('Vendas'); setOpenGroup('Comercial') }} onOrder={(id) => { setOrderSaleId(id); setPage('Ordens de serviço'); setOpenGroup('Operação') }} />
          ) : page === 'Compras' ? (
            <Purchases key={selectedStore.id} store={selectedStore} userId={user.id} onSavingChange={setSavingSale} onDirtyChange={setSaleDirty} onPayables={purchaseRights.access?.payables.view ? id => { if (leaveSaleAllowed()) { setPayablePurchaseId(id); setOpenGroup('Gestão'); setPage('Contas a pagar') } } : undefined} />
          ) : page === 'Relatórios' ? (
            <Reports key={selectedStore.id} store={selectedStore} onSavingChange={setSavingSale} />
          ) : page === 'Contas a pagar' ? (
            <Payables key={selectedStore.id} store={selectedStore} userId={user.id} initialPurchaseId={payablePurchaseId} onSavingChange={setSavingSale} onDirtyChange={setSaleDirty} />
          ) : page === 'Fornecedores' ? (
            <Suppliers key={selectedStore.id} store={selectedStore} userId={user.id} onSavingChange={setSavingSale} onDirtyChange={setSaleDirty} />
          ) : page === 'Clientes' ? (
            <section className="erp-clientes-page">
              <div className="erp-page-heading erp-list-heading">
                <div>
                  <span className="erp-kicker">CADASTROS</span>
                  <h1>Clientes</h1>
                  <p>Clientes cadastrados em {selectedStore.name}.</p>
                </div>
                {access?.customers.add && <button className="erp-action-button" type="button"
                  disabled={workspaceBusy || catalogLoading} onClick={openNewCustomer}>Novo cliente</button>}
              </div>
              {customerFormOpen && (editingCustomer ? access?.customers.change : access?.customers.add) && (
                <FormDialog title={editingCustomer ? 'Editar cliente' : 'Novo cliente'} subtitle={selectedStore.name} busy={savingCustomer} dirty={customerDirty} onClose={closeCustomerForm} actions={<button className="erp-action-button" type="submit" form="lentis-customer-form" disabled={savingCustomer}>{savingCustomer ? 'Salvando…' : editingCustomer ? 'Salvar alterações' : 'Salvar cliente'}</button>}>
                <form id="lentis-customer-form" onChangeCapture={() => setCustomerDirty(true)} className="erp-card erp-customer-form" onSubmit={(event) => void handleSaveCustomer(event)}>
                  <fieldset className="erp-window-fields" disabled={savingCustomer}>
                  <div className="erp-form-grid">
                    <label>Tipo de pessoa<select value={customerForm.person_type} onChange={(event) => setCustomerForm({ ...customerForm, person_type: event.target.value as CustomerPayload['person_type'], cpf: '', cnpj: '' })}><option value="individual">Pessoa Física</option><option value="company">Pessoa Jurídica</option></select></label>
                    <label>{customerForm.person_type === 'company' ? 'Razão social' : 'Nome completo'}<input required value={customerForm.name} onChange={(event) => setCustomerForm({ ...customerForm, name: event.target.value })} /></label>
                    {customerForm.person_type === 'company' ? <label>Nome fantasia<input value={customerForm.trade_name} onChange={(event) => setCustomerForm({ ...customerForm, trade_name: event.target.value })} /></label> : <label>RG<input value={customerForm.rg} onChange={(event) => setCustomerForm({ ...customerForm, rg: event.target.value })} /></label>}
                    <label>{customerForm.person_type === 'company' ? 'CNPJ' : 'CPF'}<input placeholder={customerForm.person_type === 'company' ? '00.000.000/0000-00' : '000.000.000-00'} value={customerForm.person_type === 'company' ? customerForm.cnpj : customerForm.cpf} onChange={(event) => setCustomerForm({ ...customerForm, [customerForm.person_type === 'company' ? 'cnpj' : 'cpf']: event.target.value })} /></label>
                    {customerForm.person_type === 'company' ? <label>Inscrição estadual<input value={customerForm.state_registration} onChange={(event) => setCustomerForm({ ...customerForm, state_registration: event.target.value })} /></label> : <label>Data de nascimento<input type="date" value={customerForm.birth_date} onChange={(event) => setCustomerForm({ ...customerForm, birth_date: event.target.value })} /></label>}
                    <label>Telefone<input value={customerForm.phone} onChange={(event) => setCustomerForm({ ...customerForm, phone: event.target.value })} /></label>
                    <label>WhatsApp<input value={customerForm.whatsapp} onChange={(event) => setCustomerForm({ ...customerForm, whatsapp: event.target.value })} /></label>
                    <label>E-mail<input type="email" value={customerForm.email} onChange={(event) => setCustomerForm({ ...customerForm, email: event.target.value })} /></label>
                    <label>CEP<input value={customerForm.zip_code} onChange={(event) => setCustomerForm({ ...customerForm, zip_code: event.target.value })} /></label>
                    <label className="erp-field-wide">Rua<input value={customerForm.street} onChange={(event) => setCustomerForm({ ...customerForm, street: event.target.value })} /></label>
                    <label>Número<input value={customerForm.address_number} onChange={(event) => setCustomerForm({ ...customerForm, address_number: event.target.value })} /></label>
                    <label>Complemento<input value={customerForm.address_complement} onChange={(event) => setCustomerForm({ ...customerForm, address_complement: event.target.value })} /></label>
                    <label>Bairro<input value={customerForm.neighborhood} onChange={(event) => setCustomerForm({ ...customerForm, neighborhood: event.target.value })} /></label>
                    <label>Cidade<input value={customerForm.city} onChange={(event) => setCustomerForm({ ...customerForm, city: event.target.value })} /></label>
                    <label>UF<input maxLength={2} value={customerForm.state} onChange={(event) => setCustomerForm({ ...customerForm, state: event.target.value.toUpperCase() })} /></label>
                    <label className="erp-field-wide">Observações<textarea value={customerForm.notes} onChange={(event) => setCustomerForm({ ...customerForm, notes: event.target.value })} /></label>
                  </div>
                  {customerFormError && <p className="erp-alert" role="alert">{customerFormError}</p>}

                  </fieldset>
                </form>
                </FormDialog>
              )}
              {access?.customers.view ? <div className="erp-card erp-customer-list-card">
                <div className="erp-list-toolbar">
                  <input aria-label="Buscar clientes" placeholder="Buscar por nome, CPF, telefone ou e-mail" value={customerSearch} onChange={(event) => setCustomerSearch(event.target.value)} />
                  <span className="erp-card-label">{filteredCustomers.length} cliente{filteredCustomers.length === 1 ? '' : 's'}</span>
                </div>
                {loadingCustomers ? <p role="status">Carregando clientes…</p>
                  : customersError ? <p className="erp-alert" role="alert">{customersError}</p>
                  : filteredCustomers.length === 0 ? <p>Nenhum cliente encontrado nesta unidade.</p>
                  : <div className="erp-customer-table-wrap"><table className="erp-customer-table"><thead><tr><th>Nome</th><th>Documento</th><th>Telefone</th><th>E-mail</th><th>Ações</th></tr></thead><tbody>{filteredCustomers.map((customer) => <tr key={customer.id}><td>{customer.name}</td><td>{customer.person_type === 'company' ? customer.cnpj || '—' : customer.cpf || '—'}</td><td>{customer.phone || '—'}</td><td>{customer.email || '—'}</td><td className="erp-customer-actions">{clinicalRights.access?.history&&<button type="button" className="erp-table-button" disabled={workspaceBusy} onClick={() => { setHistoryCustomerId(customer.id); setPage('Histórico do cliente') }}>Histórico</button>}{access?.customers.change && <button type="button" className="erp-table-button" onClick={() => openEditCustomer(customer)}>Editar</button>}{access?.customers.delete && <button type="button" className="erp-table-button is-danger" onClick={() => void handleDeleteCustomer(customer)}>Inativar</button>}</td></tr>)}</tbody></table></div>}
              </div> : <div className="erp-card"><p>Você não tem permissão para consultar a lista de clientes. O cadastro de novos registros depende da permissão de cadastrar.</p></div>}
            </section>
          ) : page === 'Visão geral' ? (
            <Dashboard key={selectedStore.id} store={selectedStore} firstName={user.first_name || user.username} onAction={dashboardAction} />
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

