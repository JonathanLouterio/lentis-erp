import { useEffect, useId, useRef, useState } from 'react'
import ProductThumbnail from './ProductThumbnail'

type Choice = { id: number; internal_code: string; name: string; thumbnail_url?: string | null; sale_price?: string; cost_price?: string }
type Props = { products: Choice[]; value: string; onChange: (value: string) => void; disabled?: boolean; label?: string }

export default function ProductPicker({ products, value, onChange, disabled, label = 'Produto' }: Props) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const id = useId()
  const selected = products.find(p => String(p.id) === value)
  const filtered = products.filter(p => `${p.internal_code} ${p.name} ${'barcode' in p ? p.barcode : ''}`.toLocaleLowerCase('pt-BR').includes(search.trim().toLocaleLowerCase('pt-BR')))
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
  return <div className="product-picker" ref={root} onKeyDown={e => { if (open && e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); setOpen(false); trigger.current?.focus() } }}>
    <span id={`${id}-label`} className="product-picker-label">{label}</span>
    <button type="button" ref={trigger} aria-labelledby={`${id}-label ${id}-value`} aria-expanded={open && !disabled} aria-controls={`${id}-choices`} disabled={disabled} onKeyDown={e => { if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true) } }} onClick={() => { setOpen(v => !v); setSearch('') }}>
      <ProductThumbnail url={selected?.thumbnail_url} name={selected?.name ?? 'Produto'} />
      <span id={`${id}-value`}>{selected ? `${selected.internal_code} · ${selected.name}` : 'Selecione um produto'}</span><span aria-hidden="true">⌄</span>
    </button>
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
