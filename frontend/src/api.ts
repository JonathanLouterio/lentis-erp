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
    body: JSON.stringify({ ...customer, ...('birth_date' in customer ? { birth_date: customer.birth_date || null } : {}) }),
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
    body: JSON.stringify({ ...customer, ...('birth_date' in customer ? { birth_date: customer.birth_date || null } : {}) }),
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
  reference_price: string | null
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
  base_total: string; financing_rate: string; financing_amount: string
  prescription: Omit<SalePrescriptionRecord, 'snapshot'> | null
  can_view_prescription: boolean
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
  discount_control: { required: boolean; limit_percentage: string; discount_percentage: string; reference_subtotal: string; discount_amount: string; state: "not_required" | "required" | "pending" | "approved" | "rejected"; request_id: number | null } | null
  discount_requests: DiscountRequest[]
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
export type PaymentMethod = { id: number; name: string; code: string; kind: PaymentKind; installment_limit: number }
export type FinancialAccount = { id: number; name: string; code: string; balance?: string; cash_box: boolean; cash_control_enabled: boolean; cash_is_open: boolean }
export type PaymentOptions = { can_view_balances?: boolean; methods: PaymentMethod[]; accounts: FinancialAccount[]; can_receive: boolean; allow_negative_stock: boolean; discount_limit_percentage: string; discount_policy_configured: boolean; can_approve_discount: boolean; discount_role: string }
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
  principal_amount: string; financing_amount: string
  id: number; method: number; account: number; method_name: string; account_name: string; kind: PaymentKind
  amount: string; installment_count: number; first_due_date: string; interval_unit: 'months' | 'days'; interval_count: number; confirmed: boolean; installments: Receivable[]
}
export type CheckoutPayment = {
  method_id: number; account_id: number; amount: string; installment_count: number
  first_due_date: string; confirmed: boolean; interval_unit?: 'months' | 'days'; interval_count?: number
}
export type CheckoutPayload = {
  financing_rate?: string
  prescription_selection?: SalePrescriptionSelection
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


export type DiscountRequest = {
  id: number; requester: string; reason: string; created_at: string; limit_percentage: string
  reference_subtotal: string; discount_amount: string; state: 'pending' | 'approve' | 'reject'
  current: boolean; can_decide: boolean; decided_by: string | null; decision_reason: string | null; decided_at: string | null
}
export function requestDiscountAuthorization(storeId: number, saleId: number, reason: string): Promise<Sale> {
  return saleWrite(storeId, `${saleId}/discount/request/`, 'POST', { reason })
}
export function decideDiscountAuthorization(storeId: number, saleId: number, requestId: number, action: 'approve' | 'reject', reason: string): Promise<Sale> {
  return saleWrite(storeId, `${saleId}/discount/${requestId}/decision/`, 'POST', { action, reason })
}


export type PaymentPreview = {
  base_total: string; financing_rate: string; financing_amount: string
  total: string
  payments: { method_name: string; account_name: string; kind: PaymentKind; amount: string; confirmed: boolean; installments: { number: number; due_date: string; amount: string }[] }[]
}
export async function getPaymentPreview(storeId: number, total: string, payments: CheckoutPayment[], financing_rate = '0'): Promise<PaymentPreview> {
  const token = await getCsrfToken()
  return request(`/api/me/sales/payment-preview/?store_id=${storeId}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
    body: JSON.stringify({ total, payments, financing_rate }),
  })
}

export type CashSession = {
  can_move: boolean; can_close: boolean;
  id: number; account: number; account_name: string; opened_by: number; owner_username: string
  opened_at: string; opening_amount: string; opening_note: string; closed_at: string | null
  closer_username: string | null; counted_amount: string | null; expected_cash: string
  difference: string | null; closing_note: string; can_operate: boolean
}
export type CashPosting = {
  id: number; kind: 'supply' | 'withdrawal' | 'receipt' | 'refund'; kind_label: string
  amount: string; reason: string; created_at: string; creator_username: string
  financial_entry: number | null; sale_id: number | null; purchase_id?: number | null
}
export type CashPage<T> = { count: number; results: T[]; next: string | null; previous: string | null }
export type CashAttempt =
  | { action: 'open'; payload: { request_id: string; account_id: number; amount: string; note: string } }
  | { action: 'move'; sessionId: number; payload: { request_id: string; kind: 'supply' | 'withdrawal'; amount: string; reason: string } }
  | { action: 'close'; sessionId: number; payload: { request_id: string; counted_amount: string; note: string } }
export function getCashOptions(storeId: number): Promise<{ accounts: FinancialAccount[] }> { return request(`/api/me/cash/options/?store_id=${storeId}`) }
export function getCashSessions(storeId: number, page = 1, status = 'all'): Promise<CashPage<CashSession>> { return request(`/api/me/cash/?store_id=${storeId}&page=${page}&status=${status}`) }
export function getCashSession(storeId: number, id: number): Promise<CashSession> { return request(`/api/me/cash/${id}/?store_id=${storeId}`) }
export function getCashPostings(storeId: number, id: number, page = 1): Promise<CashPage<CashPosting>> { return request(`/api/me/cash/${id}/postings/?store_id=${storeId}&page=${page}`) }
export async function submitCashOperation(storeId: number, attempt: CashAttempt): Promise<CashSession | CashPosting> {
  const token = await getCsrfToken()
  const suffix = attempt.action === 'open' ? '' : `${attempt.sessionId}/${attempt.action === 'move' ? 'postings/' : 'close/'}`
  return request(`/api/me/cash/${suffix}?store_id=${storeId}`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token }, body: JSON.stringify(attempt.payload) })
}

export type DashboardPeriod = { preset: 'today' | '7days' | 'month' | 'custom'; start?: string; end?: string }
export type DashboardData = {
  store_id: number; generated_at: string; today: string; timezone: string
  period: { preset: string; start: string; end: string; previous_start: string; previous_end: string }
  permissions: {sales:boolean;receipts:boolean;receivables:boolean;stock:boolean;cash:boolean}
  shortcuts:Record<InsightShortcut,boolean>
  sales: { count: number; total: string; ticket: string; previous_total: string; previous_count: number; variation: string | null } | null
  receipts: { gross: string; refunds: string; net: string } | null
  receivables: {
    customer: { count: number; amount: string }; operator: { count: number; amount: string }
    overdue: { count: number; amount: string }; due_today: { count: number; amount: string }
    attention: { id: number; sale_id: number; customer_name: string; due_date: string; remaining: string; overdue: boolean }[]
  } | null
  stock: { low_count: number; negative_count: number; items: { id: number; name: string; code: string; quantity: string; minimum: string }[] } | null
  cash: { count: number; expected_cash: string; items: { id: number; account_name: string; owner: string; opened_at: string; expected_cash: string }[] } | null
  chart: { date: string; sales_count: number|null; sales: string|null; received: string|null }[]
  recent_sales: { id: number; customer_name: string; completed_at: string; total: string }[]
}
export function getDashboard(storeId: number, period: DashboardPeriod): Promise<DashboardData> {
  const query = new URLSearchParams({ store_id: String(storeId), preset: period.preset })
  if (period.preset === 'custom') { query.set('start', period.start ?? ''); query.set('end', period.end ?? '') }
  return request(`/api/me/dashboard/?${query}`)
}

export type QuoteStatus = 'draft' | 'sent' | 'accepted' | 'rejected' | 'converted'
export type Quote = {
  actions: QuoteActions;
  id: number; store: number; customer: number | null; customer_name: string | null; creator_username: string
  status: QuoteStatus; status_label: string; is_expired: boolean; valid_until: string; notes: string
  discount_amount: string; version: number; sale: number | null; created_at: string; updated_at: string
  subtotal: string; total: string
  items: { id: number; product: number; product_name: string; product_code: string; quantity: string; unit_price: string; discount_amount: string; subtotal: string; total: string }[]
  events: { id: number; action: string; creator_username: string; reason: string; created_at: string; version: number }[]
}
export type QuotePayload = { request_id: string; expected_version?: number; customer_id: number | null; valid_until: string; notes: string; discount_amount: string; items: SaleItemPayload[] }
export type QuoteAttempt =
  | { action: 'save'; quoteId: number | null; payload: QuotePayload }
  | { action: 'send' | 'accept' | 'reject' | 'convert'; quoteId: number; payload: { request_id: string; expected_version: number; reason: string } }
export function getQuotes(storeId: number, page = 1, status = 'all'): Promise<CashPage<Quote>> { return request(`/api/me/quotes/?store_id=${storeId}&page=${page}&status=${status}`) }
export function getQuote(storeId: number, id: number): Promise<Quote> { return request(`/api/me/quotes/${id}/?store_id=${storeId}`) }
export async function submitQuoteOperation(storeId: number, attempt: QuoteAttempt): Promise<Quote> {
  const token = await getCsrfToken()
  const suffix = attempt.action === 'save' ? attempt.quoteId ? `${attempt.quoteId}/` : '' : `${attempt.quoteId}/${attempt.action}/`
  return request(`/api/me/quotes/${suffix}?store_id=${storeId}`, { method: attempt.action === 'save' && attempt.quoteId ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token }, body: JSON.stringify(attempt.payload) })
}

export const prescriptionFields = ['od_sphere','od_cylinder','od_axis','od_addition','oe_sphere','oe_cylinder','oe_axis','oe_addition','pd','od_dnp','oe_dnp'] as const
export type PrescriptionField = typeof prescriptionFields[number]
export type PrescriptionValues = Record<PrescriptionField, string | number | null> & { issued_on: string; prescriber_name: string; prescriber_registration: string; notes: string }
export type Prescription = PrescriptionValues & { id: number; store: number; customer: number; customer_name: string; version: number; is_active: boolean; creator_username: string; editor_username: string; created_at: string; updated_at: string; revisions?: { version:number; action:string; reason:string; created_at:string; creator_username:string; snapshot: PrescriptionValues & {customer_id:number;is_active:boolean} }[] }
export type PrescriptionPage = CashPage<Prescription> & {can_create: boolean;can_edit:boolean;can_archive:boolean}
export type PrescriptionAttempt = { action:'save'|'archive'; id:number|null; payload: Record<string,unknown> & {request_id:string} }
export function getPrescriptions(storeId:number, page=1, customerId='', status='active'):Promise<PrescriptionPage> {
  const query = new URLSearchParams({store_id:String(storeId),page:String(page),status})
  if(customerId) query.set('customer_id',customerId)
  return request(`/api/me/prescriptions/?${query}`)
}
export function getPrescription(storeId:number,id:number):Promise<Prescription> {return request(`/api/me/prescriptions/${id}/?store_id=${storeId}`)}
export async function savePrescription(storeId:number,attempt:PrescriptionAttempt):Promise<Prescription> {
  const token=await getCsrfToken()
  const suffix=attempt.id?`${attempt.id}/${attempt.action==='archive'?'archive/':''}`:''
  return request(`/api/me/prescriptions/${suffix}?store_id=${storeId}`,{method:attempt.id && attempt.action==='save'?'PUT':'POST',headers:{'Content-Type':'application/json','X-CSRFToken':token},body:JSON.stringify(attempt.payload)})
}

export type SalePrescriptionSelection = {prescription_id:number|null;version?:number;expected_record_id:number|null}
export type SalePrescriptionRecord = {id:number;source_id:number|null;source_version:number|null;customer:number;action:'attached'|'removed';snapshot:PrescriptionValues & {customer_id?:number;customer_name?:string;is_active?:boolean};creator_username:string;created_at:string}
export function getSalePrescriptionAccess(storeId:number):Promise<{can_view:boolean}>{return request(`/api/me/sales/prescription-access/?store_id=${storeId}`)}
export function getSalePrescriptionHistory(storeId:number,saleId:number):Promise<SalePrescriptionRecord[]>{return request(`/api/me/sales/${saleId}/prescription-history/?store_id=${storeId}`)}

export type ServiceOrderStatus = 'open'|'laboratory'|'mounting'|'checking'|'ready'|'delivered'|'cancelled'
export type ServiceOrder = {
  id:number; sale_id:number; sale_status:SaleStatus; customer_name:string; status:ServiceOrderStatus; status_label:string
  version:number; promised_on:string; laboratory:string; frame_description:string; lens_description:string; notes:string
  created_at:string; updated_at:string; overdue:boolean; has_prescription:boolean; can_change:boolean; actions:OrderActions; next_status:ServiceOrderStatus|null
  items?:{product_id:number;code:string;name:string;quantity:string}[]
  prescription?:SalePrescriptionRecord|null; can_view_prescription?:boolean
  events?:{version:number;action:string;from_status:string;to_status:string;reason:string;snapshot:Record<string,string>;creator_username:string;created_at:string}[]
}
export type ServiceOrderPage = CashPage<ServiceOrder> & {can_create:boolean}
export type ServiceOrderAttempt = {id:number|null; payload:{request_id:string;action:'create'|'update'|'advance'|'rework'|'cancel';sale_id?:number;expected_version?:number;promised_on?:string;laboratory?:string;frame_description?:string;lens_description?:string;notes?:string;reason?:string;confirmed?:boolean;target_status?:'laboratory'|'mounting'}}
export function getServiceOrders(storeId:number,page=1,status='active',overdue=false,saleId?:number):Promise<ServiceOrderPage>{
  const query=new URLSearchParams({store_id:String(storeId),page:String(page),status})
  if(overdue)query.set('overdue','1')
  if(saleId)query.set('sale_id',String(saleId))
  return request(`/api/me/service-orders/?${query}`)
}
export function getServiceOrder(storeId:number,id:number):Promise<ServiceOrder>{return request(`/api/me/service-orders/${id}/?store_id=${storeId}`)}
export async function submitServiceOrder(storeId:number,attempt:ServiceOrderAttempt):Promise<ServiceOrder>{
  const token=await getCsrfToken()
  return request(`/api/me/service-orders/${attempt.id?`${attempt.id}/`:''}?store_id=${storeId}`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':token},body:JSON.stringify(attempt.payload)})
}

export type CustomerHistorySection = 'sales'|'quotes'|'prescriptions'|'orders'|'installments'
export type CustomerHistorySummary = {
  customer:Customer; generated_at:string; permissions:{sales:boolean;quotes:boolean;prescriptions:boolean;orders:boolean;installments:boolean}
  summary:{completed_sales:number|null;draft_sales:number|null;quotes:number|null;orders:number|null;prescriptions:number|null;customer_pending:string|null;operator_pending:string|null;customer_overdue:string|null}
}
export type CustomerHistoryRecord = {
  id:number;kind:CustomerHistorySection;date:string;title:string;status:string;status_label:string;amount:string|null;sale_id:number|null
  fields:{label:string;value:string}[]
  items:{name:string;code:string;quantity:string;unit_price:string|null;total:string|null}[]
  clinical:(PrescriptionValues & {customer_id:number;is_active:boolean})|null
  remaining?:string;due_date?:string;debtor?:'customer'|'operator';overdue?:boolean
}
export function getCustomerHistorySummary(storeId:number,customerId:number):Promise<CustomerHistorySummary>{return request(`/api/me/customers/${customerId}/history/?store_id=${storeId}`)}
export function getCustomerHistoryRecords(storeId:number,customerId:number,section:CustomerHistorySection,page=1):Promise<CashPage<CustomerHistoryRecord>>{return request(`/api/me/customers/${customerId}/history/?store_id=${storeId}&section=${section}&page=${page}`)}
export function getCustomerHistoryRecord(storeId:number,customerId:number,section:CustomerHistorySection,recordId:number):Promise<CustomerHistoryRecord>{return request(`/api/me/customers/${customerId}/history/?store_id=${storeId}&section=${section}&record_id=${recordId}`)}

export type SupplierPayload = {
  person_type:'company'|'individual';name:string;trade_name:string;document:string;state_registration:string
  contact_name:string;phone:string;whatsapp:string;email:string;zip_code:string;street:string;address_number:string
  address_complement:string;neighborhood:string;city:string;state:string;notes:string
}
export type Supplier = SupplierPayload & {id:number;store:number;is_active:boolean;version:number;created_at:string;updated_at:string;events?:{version:number;action:string;action_label:string;reason:string;creator_username:string;created_at:string}[]}
export type SuppliersPage = CashPage<Supplier> & {can_create:boolean;can_edit:boolean}
export type SupplierAttempt = {id:number|null;payload:Partial<SupplierPayload> & {request_id:string;action:'create'|'update'|'archive'|'restore';expected_version?:number;reason?:string}}
export function getSuppliers(storeId:number,page=1,status='active',search=''):Promise<SuppliersPage>{const query=new URLSearchParams({store_id:String(storeId),page:String(page),status,search});return request(`/api/me/suppliers/?${query}`)}
export function getSupplier(storeId:number,id:number):Promise<Supplier>{return request(`/api/me/suppliers/${id}/?store_id=${storeId}`)}
export async function submitSupplier(storeId:number,attempt:SupplierAttempt):Promise<Supplier>{const token=await getCsrfToken();return request(`/api/me/suppliers/${attempt.id?`${attempt.id}/`:''}?store_id=${storeId}`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':token},body:JSON.stringify(attempt.payload)})}

export type PurchaseItemPayload = {product_id:number;quantity:string;unit_cost:string}
export type Purchase = {
  id:number;store:number;supplier_id:number;supplier_name:string;reference:string;document_date:string|null;notes:string
  status:'draft'|'received'|'cancelled';status_label:string;version:number;total:string;updates_cost:boolean
  created_at:string;received_at:string|null;can_edit:boolean;can_receive:boolean;actions:PurchaseActions;supplier_snapshot?:Record<string,string>
  items?: (PurchaseItemPayload & {id:number;product_code:string;product_name:string;total:string;movement_id:number|null})[]
  events?: {version:number;action:string;action_label:string;reason:string;creator_username:string;created_at:string}[]
}
export type PurchaseAttempt = {id:number|null;payload:{request_id:string;action:'create'|'update'|'receive'|'cancel';expected_version?:number;supplier_id?:number;reference?:string;document_date?:string|null;notes?:string;items?:PurchaseItemPayload[];confirmed?:boolean;update_cost?:boolean;reason?:string}}
export type PurchasesPage = CashPage<Purchase> & {can_create:boolean;can_receive:boolean}
export function getPurchases(storeId:number,page=1,status='all'):Promise<PurchasesPage>{return request(`/api/me/purchases/?store_id=${storeId}&page=${page}&status=${status}`)}
export function getPurchase(storeId:number,id:number):Promise<Purchase>{return request(`/api/me/purchases/${id}/?store_id=${storeId}`)}
export async function submitPurchase(storeId:number,attempt:PurchaseAttempt):Promise<Purchase>{const token=await getCsrfToken();return request(`/api/me/purchases/${attempt.id?`${attempt.id}/`:''}?store_id=${storeId}`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':token},body:JSON.stringify(attempt.payload)})}

export type PayablePayment = {id:number;amount:string;account_name:string;method_name:string;paid_on:string;reason:string;reversal_of:number|null;reversed:boolean;cash_posting_id:number|null;creator_username:string;created_at:string}
export type PayableInstallment = {id:number;number:number;due_date:string;amount:string;paid:string;remaining:string;status:'pending'|'partial'|'paid';overdue:boolean;payments:PayablePayment[]}
export type PayablePermissions = {can_create:boolean;can_pay:boolean;can_reverse:boolean}
export type PayablePlan = PayablePermissions & {id:number;purchase_id:number;supplier_name:string;reference:string;total:string;paid:string;remaining:string;status:'pending'|'partial'|'paid';overdue:boolean;installment_count:number;first_due_date:string;interval_unit:'months'|'days';interval_count:number;creator_username:string;created_at:string;installments?:PayableInstallment[]}
export type PayablesPage = CashPage<PayablePlan> & PayablePermissions
export type PayableOptions = PayablePermissions & {accounts:{id:number;name:string;cash_box:boolean;balance?:string}[];methods:{id:number;name:string;kind:'cash'|'pix'|'transfer'|'debit'}[]}
export type PayableAttempt =
  | {kind:'generate';payload:{request_id:string;purchase_id:number;installment_count:number;first_due_date:string;interval_unit:'months'|'days';interval_count:number}}
  | {kind:'pay';installmentId:number;payload:{request_id:string;account_id:number;method_id:number;amount:string;paid_on:string;reason:string}}
  | {kind:'reverse';paymentId:number;payload:{request_id:string;reason:string}}
export function getPayables(storeId:number,page=1,status='pending',purchaseId?:number):Promise<PayablesPage>{const query=new URLSearchParams({store_id:String(storeId),page:String(page),status});if(purchaseId)query.set('purchase_id',String(purchaseId));return request(`/api/me/payables/?${query}`)}
export function getPayable(storeId:number,id:number):Promise<PayablePlan>{return request(`/api/me/payables/${id}/?store_id=${storeId}`)}
export function getPayableOptions(storeId:number):Promise<PayableOptions>{return request(`/api/me/payables/options/?store_id=${storeId}`)}
export async function submitPayable(storeId:number,attempt:PayableAttempt):Promise<PayablePlan>{const token=await getCsrfToken();const suffix=attempt.kind==='pay'?`installments/${attempt.installmentId}/pay/`:attempt.kind==='reverse'?`payments/${attempt.paymentId}/reverse/`:'';return request(`/api/me/payables/${suffix}?store_id=${storeId}`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':token},body:JSON.stringify(attempt.payload)})}

export type ReportKind='sales'|'movements'|'receivables'|'payables'
export type ReportFilters={all_dates?:boolean;customer?:string;sale_id?:number|null;method?:string;risk?:string;aging?:string;warning_days?:number;report:ReportKind;start:string;end:string;status:'all'|'pending'|'paid'|'partial'|'overdue';debtor:'all'|'customer'|'operator';direction:'all'|'in'|'out';account_id?:number|null}
export type ReportColumn={key:string;label:string;kind:'text'|'money'|'date'|'datetime'|'integer'}
export type ReportData=CashPage<Record<string,string>> & {aging?:{key:string;label:string;count:number;amount:string;tone:string}[];title:string;description:string;basis:string;columns:ReportColumn[];summary:{key:string;label:string;value:string;kind:'money'|'integer'}[];filters:ReportFilters;generated_at:string;today:string;timezone:string;store_id:number}
export type ReportOptions={reports:{key:ReportKind;title:string;basis:string}[];accounts:{id:number;name:string;is_active:boolean}[];timezone:string;start:string;end:string;max_export_rows:number;max_print_rows:number}
function reportQuery(storeId:number,filters:ReportFilters,page=1){const query=new URLSearchParams({store_id:String(storeId),report:filters.report,start:filters.start,end:filters.end,page:String(page)});if(filters.report==='receivables'||filters.report==='payables')query.set('status',filters.status);if(filters.report==='receivables'){if(filters.all_dates){query.delete('start');query.delete('end')}query.set('debtor',filters.debtor);query.set('all_dates',String(!!filters.all_dates));for(const key of ['customer','sale_id','method','risk','aging','warning_days'] as const){const value=filters[key];if(value!==null&&value!==undefined&&value!=='')query.set(key,String(value))}};if(filters.report==='movements'){query.set('direction',filters.direction);if(filters.account_id)query.set('account_id',String(filters.account_id))}return query}
export function reportPrintUrl(storeId:number,filters:ReportFilters):string {const query=reportQuery(storeId,filters);query.set('export','print');return `/api/me/reports/?${query}`}
export function getReportOptions(storeId:number):Promise<ReportOptions>{return request(`/api/me/reports/options/?store_id=${storeId}`)}
export function getReport(storeId:number,filters:ReportFilters,page=1):Promise<ReportData>{return request(`/api/me/reports/?${reportQuery(storeId,filters,page)}`)}
export async function exportReport(storeId:number,filters:ReportFilters):Promise<{blob:Blob;filename:string}>{
  const query=reportQuery(storeId,filters);query.set('export','csv')
  let response:Response
  try{response=await fetch(`/api/me/reports/?${query}`,{headers:{Accept:'*/*'},credentials:'same-origin',cache:'no-store'})}catch{throw new ApiError('Não foi possível conectar para exportar o relatório.',0)}
  if(!response.ok){const data=await response.json().catch(()=>null);throw new ApiError(firstErrorMessage(data)||'Não foi possível exportar o relatório.',response.status)}
  if(!response.headers.get('Content-Type')?.toLowerCase().startsWith('text/csv'))throw new ApiError('O servidor retornou um arquivo inesperado.',502)
  const filename=(response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1]||'lentis-relatorio.csv').replace(/[\\/]/g,'_')
  return {blob:await response.blob(),filename}
}

// Gestão global: somente administradores do sistema.
export type ManagedMembership = { store_id: number; role: string; is_active: boolean }
export type UserManagementOptions = {
  roles: { value: string; label: string }[]
  stores: { id: number; code: string; name: string; is_active: boolean }[]
  permissions: { id: number; key: string; name: string; app: string; model: string; section: string }[]
}
export type ManagedUserSummary = {
  id: number; username: string; first_name: string; last_name: string
  is_active: boolean; protected: boolean
}
export type ManagedUser = ManagedUserSummary & {
  email: string; is_superuser: boolean; is_staff: boolean; version: string
  permission_ids: number[]; inherited_permission_ids: number[]; groups: string[]
  memberships: ManagedMembership[]
}
export type ManagedUserPayload = {
  username: string; first_name: string; last_name: string; email: string
  is_active: boolean; permission_ids: number[]; memberships: ManagedMembership[]
  password?: string; version?: string
}
export type ManagedUsersPage = { results: ManagedUserSummary[]; count: number; page: number; has_next: boolean }
export type UserAccessEvent = {
  id: number; actor: string; action: string; created_at: string
  changes: Record<string, { before: unknown; after: unknown }>
}
const userManagementPath = '/api/me/user-management/'
export function getUserManagementOptions(): Promise<UserManagementOptions> {
  return request(`${userManagementPath}options/`)
}
export function getManagedUsers(search = '', page = 1): Promise<ManagedUsersPage> {
  return request(`${userManagementPath}?${new URLSearchParams({ search, page: String(page) })}`)
}
export function getManagedUser(id: number): Promise<ManagedUser> {
  return request(`${userManagementPath}${id}/`)
}
export async function saveManagedUser(id: number | null, data: ManagedUserPayload): Promise<ManagedUser> {
  const token = await getCsrfToken()
  return request(`${userManagementPath}${id === null ? '' : `${id}/`}`, {
    method: id === null ? 'POST' : 'PATCH',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
    body: JSON.stringify(data),
  })
}
export async function resetManagedUserPassword(id: number, password: string, version: string): Promise<ManagedUser> {
  const token = await getCsrfToken()
  return request(`${userManagementPath}${id}/password/`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
    body: JSON.stringify({ password, version }),
  })
}
export function getManagedUserHistory(id: number): Promise<{ results: UserAccessEvent[] }> {
  return request(`${userManagementPath}${id}/history/`)
}

export type CatalogActions = { view: boolean; add: boolean; change: boolean; delete: boolean }
export type CatalogAccess = {
  store_id: number
  customers: CatalogActions
  products: CatalogActions
  stock: { view: boolean; add: boolean }
}
export type StockProductChoice = Pick<Product, 'id' | 'internal_code' | 'name' | 'stock_quantity' | 'minimum_stock'>
export type StockOptions = {
  store_id: number; allow_negative_stock: boolean; can_view: boolean; can_create: boolean
  products: StockProductChoice[]
}
export function getCatalogAccess(storeId: number): Promise<CatalogAccess> {
  return request(`/api/me/catalog-access/?store_id=${storeId}`)
}
export function getStockOptions(storeId: number): Promise<StockOptions> {
  return request(`/api/me/stock-options/?store_id=${storeId}`)
}


export type SaleAccess = { store_id: number; view: boolean; add: boolean; change: boolean; finalize: boolean; cancel: boolean }
export type SaleCustomerChoice = Pick<Customer, 'id' | 'name'>
export type SaleProductChoice = Pick<Product, 'id' | 'internal_code' | 'name' | 'barcode' | 'sale_price' | 'stock_quantity'>
export type SalePaymentOptions = Omit<PaymentOptions, 'accounts'> & { accounts: Omit<FinancialAccount, 'balance'>[] }
export type SaleOptions = { customers: SaleCustomerChoice[]; products: SaleProductChoice[]; payment_options: SalePaymentOptions }
export function getSaleAccess(storeId: number): Promise<SaleAccess> { return request(`/api/me/sales/access/?store_id=${storeId}`) }
export function getSaleOptions(storeId: number): Promise<SaleOptions> { return request(`/api/me/sales/options/?store_id=${storeId}`) }


export type FinanceAccess = {store_id:number;cash:{view:boolean;open:boolean;move:boolean;close:boolean};receipts:{view:boolean;receive:boolean;balances:boolean}}
export function getFinanceAccess(storeId:number):Promise<FinanceAccess>{return request(`/api/me/finance-access/?store_id=${storeId}`)}


export type QuoteActions = {view:boolean;add:boolean;change:boolean;send:boolean;accept:boolean;reject:boolean;convert:boolean;print:boolean}
export type QuoteAccess = {store_id:number;actions:QuoteActions;can_open_sale:boolean}
export type QuoteCustomerChoice = Pick<Customer,'id'|'name'>
export type QuoteProductChoice = Pick<Product,'id'|'internal_code'|'name'|'sale_price'>
export function getQuoteAccess(storeId:number):Promise<QuoteAccess>{return request(`/api/me/quotes/access/?store_id=${storeId}`)}
export function getQuoteOptions(storeId:number):Promise<{customers:QuoteCustomerChoice[];products:QuoteProductChoice[]}>{return request(`/api/me/quotes/options/?store_id=${storeId}`)}

export type OrderActions = {view:boolean;create:boolean;update:boolean;advance:boolean;rework:boolean;cancel:boolean}
export type OrderAccess = {store_id:number;actions:OrderActions}
export function getOrderAccess(storeId:number):Promise<OrderAccess>{return request(`/api/me/service-orders/access/?store_id=${storeId}`)}
export function getOrderSales(storeId:number,page:number):Promise<{results:{id:number;customer_name:string}[];next:string|null}>{return request(`/api/me/service-orders/sales/?store_id=${storeId}&page=${page}`)}

export type PurchaseActions={view:boolean;create:boolean;update:boolean;receive:boolean;cancel:boolean;update_cost:boolean}
export type PurchaseAccess={store_id:number;purchases:PurchaseActions;payables:{view:boolean;generate:boolean;pay:boolean;reverse:boolean}}
export type PurchaseOptions={results:{id:number;name:string;document:string}[];next:string|null;products:{id:number;internal_code:string;name:string;cost_price:string}[]}
export function getPurchaseAccess(storeId:number):Promise<PurchaseAccess>{return request(`/api/me/purchases/access/?store_id=${storeId}`)}
export function getPurchaseOptions(storeId:number,page:number):Promise<PurchaseOptions>{return request(`/api/me/purchases/options/?store_id=${storeId}&page=${page}`)}

export type ClinicalAccess={store_id:number;prescriptions:{view:boolean;create:boolean;update:boolean;archive:boolean};history:boolean;sections:Record<CustomerHistorySection,boolean>}
export function getClinicalAccess(storeId:number):Promise<ClinicalAccess>{return request(`/api/me/clinical-access/?store_id=${storeId}`)}
export function getPrescriptionCustomers(storeId:number,page=1):Promise<CashPage<{id:number;name:string}>>{return request(`/api/me/prescriptions/customers/?store_id=${storeId}&page=${page}`)}

export type InsightShortcut='new-sale'|'new-customer'|'receivables'|'stock'|'cash'|'sale'
export type InsightAccess={store_id:number;dashboard:boolean;sections:DashboardData['permissions'];reports:Record<ReportKind,boolean>;export:boolean;shortcuts:Record<InsightShortcut,boolean>}
export function getInsightAccess(storeId:number):Promise<InsightAccess>{return request(`/api/me/insight-access/?store_id=${storeId}`)}
export type SupplierAccess={store_id:number;actions:{view:boolean;create:boolean;update:boolean;archive:boolean;restore:boolean}}
export function getSupplierAccess(storeId:number):Promise<SupplierAccess>{return request(`/api/me/suppliers/access/?store_id=${storeId}`)}
