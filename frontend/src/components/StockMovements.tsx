import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { createStockMovement, getMyProducts, getStockMovements, getPaymentOptions } from '../api'
import type { AccessibleStore, Product, StockMovement, StockMovementType } from '../api'
import './StockMovements.css'

type Props = {
  store: AccessibleStore
  initialProductId?: string
  onSavingChange: (saving: boolean) => void
}

const quantityFormat = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 3 })
const dateFormat = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' })
const labels: Record<StockMovementType, string> = {
  entry: 'Entrada', exit: 'Saída', adjustment: 'Ajuste',
}

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : 'Não foi possível concluir a operação.'
}

function readQuantity(value: string): number | null {
  const text = value.trim().replace(',', '.')
  if (!/^\d+(?:\.\d{1,3})?$/.test(text)) return null
  const amount = Number(text)
  return Number.isFinite(amount) && amount <= 999999999.999 ? amount : null
}

export default function StockMovements({ store, initialProductId = '', onSavingChange }: Props) {
  const [products, setProducts] = useState<Product[]>([])
  const [allowNegative, setAllowNegative] = useState(false)
  const [movements, setMovements] = useState<StockMovement[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [reload, setReload] = useState(0)
  const [productId, setProductId] = useState(initialProductId)
  const [movementType, setMovementType] = useState<StockMovementType>('entry')
  const [quantity, setQuantity] = useState('')
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')
  const [success, setSuccess] = useState('')
  const [filterProduct, setFilterProduct] = useState('')
  const [filterType, setFilterType] = useState('')
  const [search, setSearch] = useState('')

  useEffect(() => {
    let ignore = false
    setLoading(true)
    setLoadError('')
    void Promise.all([getMyProducts(store.id), getStockMovements(store.id), getPaymentOptions(store.id)])
      .then(([currentProducts, history, policy]) => {
        if (ignore) return
        setProducts(currentProducts)
        setMovements(history)
        setAllowNegative(policy.allow_negative_stock)
        setProductId((current) => currentProducts.some((item) => String(item.id) === current) ? current : '')
      })
      .catch((err: unknown) => {
        if (!ignore) setLoadError(messageFrom(err))
      })
      .finally(() => { if (!ignore) setLoading(false) })
    return () => { ignore = true }
  }, [store.id, reload])

  const selectedProduct = products.find((product) => String(product.id) === productId)
  const amount = readQuantity(quantity)
  const balance = selectedProduct ? Number(selectedProduct.stock_quantity) : null
  const preview = balance !== null && amount !== null
    ? movementType === 'entry' ? balance + amount : movementType === 'exit' ? balance - amount : amount
    : null
  const negativeBlocked = preview !== null && preview < 0 && movementType === "exit" && !allowNegative
  const invalidPreview = preview !== null && (negativeBlocked || Math.abs(preview) > 999999999.999)
  const lowStock = products.filter((product) => Number(product.stock_quantity) <= Number(product.minimum_stock)).length
  const historyProducts = new Map<number, string>()
  products.forEach((product) => historyProducts.set(product.id, `${product.internal_code} — ${product.name}`))
  movements.forEach((movement) => {
    if (!historyProducts.has(movement.product)) {
      historyProducts.set(movement.product, `${movement.product_code} — ${movement.product_name} (inativo)`)
    }
  })
  const filtered = movements.filter((movement) => {
    if (filterProduct && String(movement.product) !== filterProduct) return false
    if (filterType && movement.movement_type !== filterType) return false
    const query = search.trim().toLocaleLowerCase('pt-BR')
    return !query || [movement.product_code, movement.product_name, movement.reason, movement.created_by_username]
      .some((value) => value.toLocaleLowerCase('pt-BR').includes(query))
  })

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (saving) return
    setFormError('')
    setSuccess('')
    if (!selectedProduct) {
      setFormError('Selecione um produto ativo desta unidade.')
      return
    }
    if (amount === null || (movementType !== 'adjustment' && amount === 0)) {
      setFormError('Informe uma quantidade válida, com até três casas decimais. Apenas o ajuste aceita zero.')
      return
    }
    if (invalidPreview) {
      setFormError(negativeBlocked ? 'Estoque insuficiente para esta saída.' : 'O saldo resultante excede o limite permitido.')
      return
    }
    if (!reason.trim()) {
      setFormError('Informe o motivo da movimentação.')
      return
    }
    setSaving(true)
    onSavingChange(true)
    try {
      const saved = await createStockMovement(store.id, {
        product_id: selectedProduct.id,
        movement_type: movementType,
        quantity: amount.toFixed(3),
        reason: reason.trim(),
      })
      setMovements((current) => [saved, ...current])
      setProducts((current) => current.map((product) => product.id === saved.product
        ? { ...product, stock_quantity: saved.balance_after } : product))
      setQuantity('')
      setReason('')
      setSuccess(`${labels[saved.movement_type]} ${saved.movement_type === 'adjustment' ? 'registrado' : 'registrada'} para ${saved.product_name}. Saldo: ${quantityFormat.format(Number(saved.balance_after))}.`)
    } catch (err) {
      setFormError(messageFrom(err))
    } finally {
      setSaving(false)
      onSavingChange(false)
    }
  }

  function refresh() {
    if (saving || loading) return
    setSuccess('')
    setFormError('')
    setReload((value) => value + 1)
  }

  return (
    <section className="erp-stock-page">
      <div className="erp-page-heading erp-list-heading">
        <div>
          <span className="erp-kicker">OPERAÇÃO</span>
          <h1>Estoque</h1>
          <p>Movimentações e saldos de {store.name}.</p>
        </div>
        <button type="button" className="erp-secondary-button" disabled={loading || saving} onClick={refresh}>
          {loading ? 'Carregando…' : 'Atualizar saldos e histórico'}
        </button>
      </div>
      {loading ? <div className="erp-card" role="status">Carregando estoque…</div>
        : loadError ? <div className="erp-card"><p className="erp-alert" role="alert">{loadError}</p>
          <button type="button" className="erp-action-button" onClick={refresh}>Tentar novamente</button></div>
        : <>
          <div className="erp-stock-summary">
            <div className="erp-card"><span className="erp-card-label">Produtos ativos</span><strong>{products.length}</strong></div>
            <div className="erp-card"><span className="erp-card-label">No mínimo ou abaixo</span><strong>{lowStock}</strong></div>
            <div className="erp-card"><span className="erp-card-label">Movimentações registradas</span><strong>{movements.length}</strong></div>
          </div>
          {success && <p className="erp-stock-success" role="status">{success}</p>}
          <form className="erp-card erp-customer-form" onSubmit={(event) => void submit(event)} aria-busy={saving}>
            <div className="erp-form-heading"><div><span className="erp-card-label">CONTROLE DE SALDO</span><h2>Nova movimentação</h2></div></div>
            {products.length === 0 ? <p>Cadastre um produto ativo nesta unidade para registrar movimentações.</p>
              : <>
                <fieldset className="erp-stock-fieldset" disabled={saving}>
                  <div className="erp-form-grid">
                    <label className="erp-field-wide">Produto
                      <select required value={productId} onChange={(event) => { setProductId(event.target.value); setFormError(''); setSuccess('') }}>
                        <option value="">Selecione o produto</option>
                        {products.map((product) => <option key={product.id} value={String(product.id)}>{product.internal_code} — {product.name}</option>)}
                      </select>
                    </label>
                    <label>Tipo de movimentação
                      <select value={movementType} onChange={(event) => { setMovementType(event.target.value as StockMovementType); setFormError('') }}>
                        <option value="entry">Entrada</option><option value="exit">Saída</option><option value="adjustment">Ajuste de saldo</option>
                      </select>
                    </label>
                    <label>{movementType === 'adjustment' ? 'Saldo final contado' : 'Quantidade movimentada'}
                      <input required inputMode="decimal" pattern="[0-9]+([.,][0-9]{1,3})?" value={quantity}
                        placeholder={movementType === 'adjustment' ? 'Ex.: 0 ou 8,5' : 'Ex.: 2 ou 2,5'}
                        onChange={(event) => { setQuantity(event.target.value); setFormError('') }} />
                    </label>
                    <label className="erp-field-wide">Motivo
                      <textarea required maxLength={255} value={reason} placeholder="Ex.: recebimento de mercadoria, saída ou conferência física"
                        onChange={(event) => setReason(event.target.value)} />
                    </label>
                  </div>
                </fieldset>
                <p className="erp-stock-hint">{movementType === 'adjustment'
                  ? 'O ajuste substitui o saldo pelo total contado. Para zerar o estoque, informe 0.'
                  : 'Entrada acrescenta e saída desconta a quantidade informada.'}</p>
                {selectedProduct && <div className="erp-stock-preview" aria-live="polite">
                  <span>Saldo atual <strong>{quantityFormat.format(balance ?? 0)}</strong></span>
                  <span className={invalidPreview ? 'is-invalid' : ''}>Saldo previsto <strong>{preview === null ? '—' : quantityFormat.format(preview)}</strong></span>
                </div>}
                <p className="erp-stock-hint">O saldo será conferido novamente ao registrar.</p>
                {invalidPreview && !formError && <p className="erp-alert" role="alert">{negativeBlocked
                  ? 'Estoque insuficiente para esta saída.' : 'O saldo resultante excede o limite permitido.'}</p>}
                {preview !== null && preview < 0 && !invalidPreview && <p className="erp-alert" role="status">A movimentação será registrada com saldo negativo: {quantityFormat.format(preview)}.</p>}
                {formError && <p className="erp-alert" role="alert">{formError}</p>}
                <button type="submit" className="erp-action-button" disabled={saving || !selectedProduct || invalidPreview}>
                  {saving ? 'Registrando…' : movementType === 'adjustment' ? 'Registrar ajuste' : 'Registrar movimentação'}
                </button>
              </>}
          </form>
          <div className="erp-card erp-customer-list-card">
            <div className="erp-form-heading"><h2>Histórico</h2><span className="erp-card-label">{filtered.length} registro{filtered.length === 1 ? '' : 's'}</span></div>
            <div className="erp-stock-filters">
              <label>Produto<select value={filterProduct} onChange={(event) => setFilterProduct(event.target.value)}>
                <option value="">Todos os produtos</option>
                {[...historyProducts].sort((a, b) => a[1].localeCompare(b[1], 'pt-BR')).map(([id, name]) => <option key={id} value={String(id)}>{name}</option>)}
              </select></label>
              <label>Tipo<select value={filterType} onChange={(event) => setFilterType(event.target.value)}>
                <option value="">Todos os tipos</option><option value="entry">Entrada</option><option value="exit">Saída</option><option value="adjustment">Ajuste</option>
              </select></label>
              <label>Buscar<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Produto, motivo ou usuário" /></label>
            </div>
            {filtered.length === 0 ? <p>Nenhuma movimentação encontrada.</p>
              : <div className="erp-customer-table-wrap"><table className="erp-customer-table erp-stock-table">
                <caption className="erp-stock-caption">Movimentações de {store.name}, da mais recente para a mais antiga.</caption>
                <thead><tr><th>Data e hora</th><th>Produto</th><th>Tipo</th><th>Quantidade</th><th>Variação</th><th>Saldo anterior</th><th>Saldo final</th><th>Motivo</th><th>Usuário</th></tr></thead>
                <tbody>{filtered.map((movement) => <tr key={movement.id}>
                  <td><time dateTime={movement.created_at}>{dateFormat.format(new Date(movement.created_at))}</time></td>
                  <td><strong>{movement.product_code}</strong><span className="erp-stock-product-name">{movement.product_name}</span></td>
                  <td><span className={`erp-stock-badge is-${movement.movement_type}`}>{labels[movement.movement_type]}</span></td>
                  <td>{quantityFormat.format(Number(movement.quantity))}{movement.movement_type === 'adjustment' && <small className="erp-stock-product-name">Saldo contado</small>}</td>
                  <td>{Number(movement.quantity_change) > 0 ? '+' : ''}{quantityFormat.format(Number(movement.quantity_change))}</td>
                  <td>{quantityFormat.format(Number(movement.balance_before))}</td><td>{quantityFormat.format(Number(movement.balance_after))}</td>
                  <td className="erp-stock-reason">{movement.reason}</td><td>{movement.created_by_username}</td>
                </tr>)}</tbody>
              </table></div>}
          </div>
        </>}
    </section>
  )
}
