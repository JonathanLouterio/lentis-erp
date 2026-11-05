import { useState } from 'react'
import './ProductPhotos.css'

export default function ProductThumbnail({ url, name, large = false }: { url?: string | null; name: string; large?: boolean }) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null)
  return <span className={`product-thumbnail${large ? ' is-large' : ''}`}>
    {url && failedUrl !== url ? <img src={url} alt={name} loading="lazy" decoding="async" onError={() => setFailedUrl(url)} /> :
      <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2" role="img" aria-label={`Sem foto: ${name}`}><path d="m7 27 3-10h8l2 4h8l2-4h8l3 10M7 27a7 7 0 1 0 14 0m6 0a7 7 0 1 0 14 0M21 27a4 4 0 0 1 6 0" /></svg>}
  </span>
}
