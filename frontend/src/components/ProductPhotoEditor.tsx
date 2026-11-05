import { useEffect, useState } from 'react'
import type { ProductGalleryChange, ProductPhoto } from '../api'
import ProductThumbnail from './ProductThumbnail'

type Props = { photos: ProductPhoto[]; value: ProductGalleryChange; onChange: (value: ProductGalleryChange) => void; disabled?: boolean }
function PhotoPreview({ file, url }: { file?: File; url?: string }) {
  const [preview, setPreview] = useState('')
  useEffect(() => {
    if (!file) return
    const next = URL.createObjectURL(file)
    setPreview(next)
    return () => URL.revokeObjectURL(next)
  }, [file])
  return <ProductThumbnail url={file ? preview : url} name="Prévia da foto do produto" large />
}

export default function ProductPhotoEditor({ photos, value, onChange, disabled }: Props) {
  const [error, setError] = useState('')
  const occupied = [1, 2, 3].filter(slot => value.files[slot] || (photos.some(p => p.slot === slot) && !value.remove.includes(slot)))
  function choose(slot: number, file?: File) {
    if (!file) return
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) { setError('Escolha uma foto JPG, PNG ou WebP de até 5 MB.'); return }
    setError('')
    onChange({ ...value, remove: value.remove.filter(n => n !== slot), files: { ...value.files, [slot]: file }, primary: value.primary ?? slot })
  }
  function remove(slot: number) {
    const files = { ...value.files }; delete files[slot]
    const remaining = occupied.filter(n => n !== slot)
    onChange({ ...value, files, remove: [...new Set([...value.remove, slot])], primary: value.primary === slot ? remaining[0] ?? null : value.primary })
  }
  return <section className="product-photo-editor" aria-label="Fotos do produto">
    <div className="product-photo-heading"><div><h3>Uma vitrine para o produto</h3><p>Adicione frente, lateral e detalhes. A principal aparece nas listas e na seleção para venda e compra.</p></div><strong>{occupied.length}/3 fotos</strong></div>
    <p>JPG, PNG ou WebP · até 5 MB e 16 megapixels por foto. As alterações serão aplicadas ao salvar o produto.</p>
    {error && <p className="erp-alert" role="alert">{error}</p>}
    <div className="product-photo-slots">{[1, 2, 3].map(slot => {
      const exists = occupied.includes(slot), main = value.primary === slot
      return <article className={main ? 'is-primary' : ''} key={slot}>
        <div className="product-photo-badge">Foto {slot}{main && <strong>Principal</strong>}</div>
        <PhotoPreview file={value.files[slot]} url={!value.remove.includes(slot) ? photos.find(p => p.slot === slot)?.url : undefined} />
        <label className="product-upload-label">{exists ? 'Trocar foto' : 'Adicionar foto'}<input aria-label={`Selecionar foto ${slot}`} type="file" accept="image/jpeg,image/png,image/webp" disabled={disabled} onChange={e => { choose(slot, e.target.files?.[0]); e.target.value = '' }} /></label>
        {exists && <div className="product-photo-actions"><button type="button" disabled={disabled || main} onClick={() => onChange({ ...value, primary: slot })}>{main ? 'Foto principal' : 'Usar como principal'}</button><button type="button" disabled={disabled} onClick={() => remove(slot)}>Remover</button></div>}
      </article>
    })}</div>
  </section>
}
