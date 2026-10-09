export type ThemePreference = 'light' | 'dark' | 'system'

export type CurrentUser = {
  id: number
  username: string
  first_name: string
  last_name: string
  theme: ThemePreference
}

export type AccessibleStore = {
  id: number
  code: string
  name: string
  role: string
  role_label: string
}

export type Customer = {
  id: number
  store: number
  store_name: string
  person_type: 'individual' | 'company'
  name: string
  trade_name: string
  cpf: string | null
  cnpj: string | null
  rg: string
  state_registration: string
  birth_date: string | null
  phone: string
  whatsapp: string
  email: string
  zip_code: string
  street: string
  address_number: string
  address_complement: string
  neighborhood: string
  city: string
  state: string
  notes: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export type CustomerPayload = {
  person_type: 'individual' | 'company'
  name: string
  trade_name: string
  cpf: string
  cnpj: string
  rg: string
  state_registration: string
  birth_date: string
  phone: string
  whatsapp: string
  email: string
  zip_code: string
  street: string
  address_number: string
  address_complement: string
  neighborhood: string
  city: string
  state: string
  notes: string
}

export type NewCustomer = CustomerPayload

export type Product = {
  id: number
  store: number
  store_name: string
  internal_code: string
  barcode: string
  name: string
  brand: string
  category: string
  cost_price: string
  sale_price: string
  stock_quantity: string
  minimum_stock: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export type ProductPayload = {
  internal_code: string
  barcode: string
  name: string
  brand: string
  category: string
  cost_price: string
  sale_price: string
  minimum_stock: string
}

export type StockMovementType = 'entry' | 'exit' | 'adjustment'

export type StockMovement = {
  id: number
  store: number
  store_name: string
  product: number
  product_name: string
  product_code: string
  movement_type: StockMovementType
  movement_type_label: string
  quantity: string
  quantity_change: string
  balance_before: string
  balance_after: string
  reason: string
  created_by: number
  created_by_username: string
  created_at: string
}

export type StockMovementPayload = {
  product_id: number
  movement_type: StockMovementType
  quantity: string
  reason: string
}

function firstErrorMessage(value: unknown): string | undefined {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) {
    for (const item of value) {
      const message = firstErrorMessage(item)
      if (message) return message
    }
  } else if (value && typeof value === 'object') {
    for (const item of Object.values(value)) {
      const message = firstErrorMessage(item)
      if (message) return message
    }
  }
  return undefined
}

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  headers.set('Accept', 'application/json')

  let response: Response
  try {
    response = await fetch(path, {
      ...options,
      headers,
      credentials: 'same-origin',
      cache: 'no-store',
    })
  } catch {
    throw new ApiError(
      'Não foi possível conectar. Verifique sua conexão e tente novamente.',
      0,
    )
  }

  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const message = typeof data?.detail === 'string'
      ? data.detail
      : firstErrorMessage(data) || 'Não foi possível concluir a operação. Tente novamente.'
    throw new ApiError(message, response.status)
  }
  if (response.status === 204) {
    return undefined as T
  }
  if (data === null) {
    throw new ApiError('O servidor retornou uma resposta inesperada.', 502)
  }
  return data as T
}

async function getCsrfToken(): Promise<string> {
  const data = await request<{ csrfToken: string }>('/api/auth/csrf/')
  return data.csrfToken
}

export function getCurrentUser(): Promise<CurrentUser> {
  return request<CurrentUser>('/api/me/')
}

export async function signIn(username: string, password: string): Promise<CurrentUser> {
  const token = await getCsrfToken()
  const data = await request<{ user: CurrentUser; csrfToken: string }>(
    '/api/auth/login/',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
      body: JSON.stringify({ username, password }),
    },
  )
  return data.user
}

export async function signOut(): Promise<void> {
  const token = await getCsrfToken()
  await request('/api/auth/logout/', {
    method: 'POST',
    headers: { 'X-CSRFToken': token },
  })
}

export function getMyStores(): Promise<AccessibleStore[]> {
  return request<AccessibleStore[]>('/api/me/stores/')
}

export function getMyCustomers(storeId: number): Promise<Customer[]> {
  return request<Customer[]>(`/api/me/customers/?store_id=${storeId}`)
}

export async function createCustomer(
  storeId: number,
  customer: NewCustomer,
): Promise<Customer> {
  const token = await getCsrfToken()
  return request<Customer>(`/api/me/customers/?store_id=${storeId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
    body: JSON.stringify(customer),
  })
}

export async function updateCustomer(
  storeId: number,
  customerId: number,
  customer: Partial<CustomerPayload>,
): Promise<Customer> {
  const token = await getCsrfToken()
  return request<Customer>(`/api/me/customers/${customerId}/?store_id=${storeId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
    body: JSON.stringify(customer),
  })
}

export async function deleteCustomer(storeId: number, customerId: number): Promise<void> {
  const token = await getCsrfToken()
  await request(`/api/me/customers/${customerId}/?store_id=${storeId}`, {
    method: 'DELETE',
    headers: { 'X-CSRFToken': token },
  })
}

export function getMyProducts(storeId: number): Promise<Product[]> {
  return request<Product[]>(`/api/me/products/?store_id=${storeId}`)
}

export async function createProduct(storeId: number, product: ProductPayload): Promise<Product> {
  const token = await getCsrfToken()
  return request<Product>(`/api/me/products/?store_id=${storeId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
    body: JSON.stringify(product),
  })
}

export async function updateProduct(
  storeId: number,
  productId: number,
  product: Partial<ProductPayload>,
): Promise<Product> {
  const token = await getCsrfToken()
  return request<Product>(`/api/me/products/${productId}/?store_id=${storeId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
    body: JSON.stringify(product),
  })
}

export async function deleteProduct(storeId: number, productId: number): Promise<void> {
  const token = await getCsrfToken()
  await request(`/api/me/products/${productId}/?store_id=${storeId}`, {
    method: 'DELETE',
    headers: { 'X-CSRFToken': token },
  })
}

export function getStockMovements(storeId: number): Promise<StockMovement[]> {
  return request<StockMovement[]>(`/api/me/stock-movements/?store_id=${storeId}`)
}

export async function createStockMovement(
  storeId: number,
  movement: StockMovementPayload,
): Promise<StockMovement> {
  const token = await getCsrfToken()
  return request<StockMovement>(`/api/me/stock-movements/?store_id=${storeId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
    body: JSON.stringify(movement),
  })
}

export async function updateTheme(
  theme: ThemePreference,
): Promise<{ theme: ThemePreference }> {
  const token = await getCsrfToken()
  return request<{ theme: ThemePreference }>('/api/me/preferences/', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
    body: JSON.stringify({ theme }),
  })
}

export type SaleStatus = 'draft' | 'completed' | 'cancelled'

export type SaleItem = {
  id: number
  product: number
  product_code: string
  product_name: string
  quantity: string
  unit_price: string
  discount_amount: string
  subtotal: string
  total: string
}

export type SaleEvent = {
  id: number
  event_type: 'completed' | 'cancelled'
  event_label: string
  created_by: number
  creator_username: string
  reason: string
  created_at: string
}

export type Sale = {
  id: number
  store: number
  store_name: string
  customer: number | null
  customer_name: string | null
  created_by: number
  creator_username: string
  status: SaleStatus
  status_label: string
  notes: string
  created_at: string
  updated_at: string
  completed_at: string | null
  cancelled_at: string | null
  cancellation_reason: string
  items: SaleItem[]
  events: SaleEvent[]
  subtotal: string
  discount_total: string
  total: string
  discount_amount: string
  payments: SalePayment[]
  stock_warnings: { product: number; product_code: string; product_name: string; balance_before: string; balance_after: string }[]
  financial_status: "planned" | "none" | "recorded" | "legacy"
  can_edit: boolean
  can_finalize: boolean
  can_cancel: boolean
}

export type SalesPage = {
  count: number
  next: string | null
  previous: string | null
  results: Sale[]
}

export type SaleItemPayload = {
  product_id: number
  quantity: string
  unit_price: string
  discount_amount: string
}

export function getSales(storeId: number, page = 1, status: SaleStatus | '' = ''): Promise<SalesPage> {
  const query = new URLSearchParams({ store_id: String(storeId), page: String(page) })
  if (status) query.set('status', status)
  return request<SalesPage>(`/api/me/sales/?${query}`)
}

export function getSale(storeId: number, saleId: number): Promise<Sale> {
  return request<Sale>(`/api/me/sales/${saleId}/?store_id=${storeId}`)
}

async function saleWrite(
  storeId: number, suffix: string, method: 'POST' | 'PATCH' | 'DELETE', data?: unknown,
): Promise<Sale> {
  const token = await getCsrfToken()
  return request<Sale>(`/api/me/sales/${suffix}?store_id=${storeId}`, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
    ...(data === undefined ? {} : { body: JSON.stringify(data) }),
  })
}

export function createSale(storeId: number): Promise<Sale> {
  return saleWrite(storeId, '', 'POST', {})
}

export function updateSale(storeId: number, saleId: number, data: { customer_id: number | null; notes: string }): Promise<Sale> {
  return saleWrite(storeId, `${saleId}/`, 'PATCH', data)
}

export function addSaleItem(storeId: number, saleId: number, item: SaleItemPayload): Promise<Sale> {
  return saleWrite(storeId, `${saleId}/items/`, 'POST', item)
}

export function updateSaleItem(storeId: number, saleId: number, itemId: number, item: SaleItemPayload): Promise<Sale> {
  return saleWrite(storeId, `${saleId}/items/${itemId}/`, 'PATCH', item)
}

export function removeSaleItem(storeId: number, saleId: number, itemId: number): Promise<Sale> {
  return saleWrite(storeId, `${saleId}/items/${itemId}/`, 'DELETE')
}

export function finalizeSale(storeId: number, saleId: number): Promise<Sale> {
  return saleWrite(storeId, `${saleId}/finalize/`, 'POST', {})
}

export function cancelSale(storeId: number, saleId: number, reason: string): Promise<Sale> {
  return saleWrite(storeId, `${saleId}/cancel/`, 'POST', { reason })
}

export type PaymentKind = 'cash' | 'pix' | 'transfer' | 'debit' | 'credit' | 'store_credit' | 'boleto'
export type PaymentMethod = { id: number; name: string; code: string; kind: PaymentKind }
export type FinancialAccount = { id: number; name: string; code: string; balance: string }
export type PaymentOptions = { methods: PaymentMethod[]; accounts: FinancialAccount[]; can_receive: boolean; allow_negative_stock: boolean }
export type FinancialEntry = {
  id: number; account: number; account_name: string; method_name: string; amount: string
  created_at: string; creator_username: string; reason: string; reversal_of: number | null
}
export type Receivable = {
  id: number; sale_id: number; number: number; installment_count: number; due_date: string
  amount: string; paid_amount: string; remaining_amount: string; status: 'pending' | 'partial' | 'paid' | 'cancelled'
  debtor: 'customer' | 'operator'; customer_name: string; method_name: string; account_name: string
  can_receive: boolean; entries: FinancialEntry[]
}
export type SalePayment = {
  id: number; method: number; account: number; method_name: string; account_name: string; kind: PaymentKind
  amount: string; installment_count: number; first_due_date: string; confirmed: boolean; installments: Receivable[]
}
export type CheckoutPayment = {
  method_id: number; account_id: number; amount: string; installment_count: number
  first_due_date: string; confirmed: boolean
}
export type CheckoutPayload = {
  request_id: string; sale_id: number | null; action: 'draft' | 'complete'; customer_id: number | null
  notes: string; discount_amount: string; items: SaleItemPayload[]; payments: CheckoutPayment[]
}
export type ReceivablesPage = { count: number; next: string | null; previous: string | null; results: Receivable[] }

export function getPaymentOptions(storeId: number): Promise<PaymentOptions> {
  return request(`/api/me/sales/payment-options/?store_id=${storeId}`)
}
export function submitCheckout(storeId: number, data: CheckoutPayload): Promise<Sale> {
  return saleWrite(storeId, 'checkout/', 'POST', data)
}
export function getReceivables(storeId: number, page = 1, status = 'pending', debtor = ''): Promise<ReceivablesPage> {
  const query = new URLSearchParams({ store_id: String(storeId), page: String(page), status })
  if (debtor) query.set('debtor', debtor)
  return request(`/api/me/receivables/?${query}`)
}
export async function receiveInstallment(storeId: number, receivableId: number, data: {
  request_id: string; account_id: number; method_id: number; amount: string
}): Promise<Receivable> {
  const token = await getCsrfToken()
  return request(`/api/me/receivables/${receivableId}/receive/?store_id=${storeId}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token }, body: JSON.stringify(data),
  })
}
