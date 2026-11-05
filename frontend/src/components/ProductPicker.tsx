import { useEffect, useId, useRef, useState } from 'react'
import { CodeCamera, CodeScanButton, readProductCode } from './ProductCodeField'
import ProductThumbnail from './ProductThumbnail'

type Choice = { id: number; internal_code: string; name: string; barcode?: string | null; thumbnail_url?: string | null; sale_price?: string; cost_price?: string }
type Props = { products: Choice[]; value: string; onChange: (value: string) => void; disabled?: boolean; label?: string; allowCamera?: boolean }

export default function ProductPicker({ products, value, onChange, disabled, label = 'Produto', allowCamera = false }: Props) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [scanning, setScanning] = useState(false)
  const [scanFeedback, setScanFeedback] = useState<{ text: string; error: boolean } | null>(null)
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const scanButton = useRef<HTMLButtonElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const id = useId()
  const selected = products.find(p => String(p.id) === value)
  const filtered = products.filter(p => `${p.internal_code} ${p.name} ${p.barcode ?? ''}`.toLocaleLowerCase('pt-BR').includes(search.trim().toLocaleLowerCase('pt-BR')))
  useEffect(() => {
    if (open) {
      input.current?.focus({ preventScroll: true })
      root.current?.scrollIntoView({ block: 'center' })
    }
  }, [open])
  useEffect(() => {
    const close = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false) }
    document.addEventListener('pointerdown', close)
    return () => document.removeEventListener('pointerdown', close)
  }, [])
  if (disabled && scanning) setScanning(false)

  function finishScan(text: string, error: boolean) {
    setScanning(false)
    setScanFeedback({ text, error })
    scanButton.current?.focus({ preventScroll: true })
  }

  function selectScannedProduct(raw: string) {
    if (disabled) return
    const code = readProductCode(raw)
    if (!code) {
      finishScan('Código inválido. Leia um código de produto com até 30 caracteres ou use a busca manual.', true)
      return
    }
    const product = products.find(item => item.barcode === code)
    if (!product) {
      finishScan('Nenhum produto ativo desta unidade tem esse código. Tente novamente ou use a busca manual.', true)
      return
    }
    onChange(String(product.id))
    const price = product.sale_price === undefined ? '' : ` · ${Number(product.sale_price).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}`
    finishScan(`${product.name}${price}. Confira e toque em Adicionar.`, false)
  }

  function toggleManualPicker() {
    setScanning(false)
    setScanFeedback(null)
    setSearch('')
    setOpen(value => !value)
  }

  return <div className="product-picker" ref={root} onKeyDown={e => {
    if (e.key !== 'Escape' || (!open && !scanning)) return
    e.preventDefault()
    e.stopPropagation()
    if (scanning) { setScanning(false); scanButton.current?.focus() }
    else { setOpen(false); trigger.current?.focus() }
  }}>
    <span id={`${id}-label`} className="product-picker-label">{label}</span>
    <div className="product-picker-row">
      <button type="button" className="product-picker-trigger" ref={trigger} aria-labelledby={`${id}-label ${id}-value`} aria-expanded={open && !disabled} aria-controls={`${id}-choices`} disabled={disabled} onKeyDown={e => {
        if (e.key === 'ArrowDown') {
          e.preventDefault()
          if (!open) toggleManualPicker()
        }
      }} onClick={toggleManualPicker}>
        <ProductThumbnail url={selected?.thumbnail_url} name={selected?.name ?? 'Produto'} />
        <span id={`${id}-value`}>{selected ? `${selected.internal_code} · ${selected.name}` : 'Selecione um produto'}</span><span aria-hidden="true">⌄</span>
      </button>
      {allowCamera && <CodeScanButton ref={scanButton} scanning={scanning} disabled={disabled} cameraId={`${id}-camera`} onToggle={() => {
        setScanFeedback(null)
        if (scanning) { setScanning(false); return }
        setOpen(false)
        onChange('')
        setScanning(true)
      }} />}
    </div>
    {allowCamera && <div className="product-picker-camera" id={`${id}-camera`}>
      {scanning && !disabled && <CodeCamera onCode={selectScannedProduct} onError={message => finishScan(message, true)} />}
      {scanFeedback && value && !scanFeedback.error && <p className="erp-sales-hint" role="status">{scanFeedback.text}</p>}
      {scanFeedback?.error && <p className="erp-alert" role="alert">{scanFeedback.text}</p>}
    </div>}
    {open && !disabled && <div className="product-picker-panel" id={`${id}-choices`}>
      <label htmlFor={`${id}-search`}>Buscar por nome, código ou código de barras</label>
      <input id={`${id}-search`} ref={input} type="search" value={search} onChange={e => setSearch(e.target.value)} />
      <ul aria-label="Produtos encontrados">{filtered.slice(0, 50).map(p => <li key={p.id}><button type="button" aria-pressed={value === String(p.id)} onClick={() => { onChange(String(p.id)); setOpen(false); trigger.current?.focus() }}>
        <ProductThumbnail url={p.thumbnail_url} name={p.name} /><span><strong>{p.name}</strong><small>{p.internal_code}{(p.sale_price ?? p.cost_price) !== undefined && ` · ${Number(p.sale_price ?? p.cost_price).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}`}</small></span>
      </button></li>)}</ul>
      {!filtered.length && <p>Nenhum produto encontrado.</p>}
      {filtered.length > 50 && <p>Exibindo 50 de {filtered.length}. Refine a busca para encontrar o produto.</p>}
    </div>}
  </div>
}
