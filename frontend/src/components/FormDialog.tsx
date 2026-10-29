import { useEffect, useId, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import './WorkspaceVisual.css'

type Props = {
  title: string
  subtitle?: string
  sectionLabel?: string
  wide?: boolean
  notice?: string
  children: ReactNode
  actions?: ReactNode
  busy?: boolean
  dirty?: boolean
  onClose: () => void
}

/** Native modal: the rest of the workspace is inert while this window is open. */
export default function FormDialog({ title, subtitle, sectionLabel = 'CADASTROS', wide = false, notice = '', children, actions, busy = false, dirty = false, onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  const [confirmClose, setConfirmClose] = useState(false)
  useEffect(() => {
    const dialog = ref.current!
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    dialog.showModal()
    return () => {
      dialog.close()
      if (opener?.isConnected) opener.focus({ preventScroll: true })
    }
  }, [])
  useEffect(() => {
    if (notice) ref.current?.querySelector('.erp-window-body')?.scrollTo({ top: 0 })
  }, [notice])
  useEffect(() => {
    if (!dirty && !busy) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty, busy])
  function requestClose() {
    if (busy) return
    if (dirty) setConfirmClose(true)
    else onClose()
  }
  return <dialog ref={ref} className={`erp-window${wide ? ' erp-window-wide' : ''}`} aria-labelledby={titleId}
    onCancel={event => { event.preventDefault(); requestClose() }}
    onKeyDown={event => {
      if (event.key !== 'Tab') return
      const nodes = [...event.currentTarget.querySelectorAll<HTMLElement>('button, input, select, textarea, a[href], summary, [tabindex="0"]')]
        .filter(node => !node.matches(':disabled') && node.tabIndex >= 0 && node.getClientRects().length > 0)
      const first = nodes[0], last = nodes[nodes.length - 1]
      if (!first) { event.preventDefault(); return }
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }}>
    <header className="erp-window-heading">
      <div><span className="erp-window-kicker">LENTIS · {sectionLabel}</span><h2 id={titleId}>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>
      <button type="button" className="erp-window-close" aria-label="Fechar janela" disabled={busy} onClick={requestClose}>×</button>
    </header>
    <div className="erp-window-body" aria-busy={busy}>{children}</div>
    <footer className="erp-window-footer">
      {confirmClose && dirty ? <div className="erp-window-discard" role="alert">
        <span>Há alterações não salvas. Deseja descartá-las?</span>
        <button type="button" disabled={busy} onClick={() => setConfirmClose(false)}>Continuar editando</button>
        <button type="button" disabled={busy} className="erp-window-danger" onClick={onClose}>Descartar alterações</button>
      </div> : <><span>{busy ? 'Aguarde a conclusão da operação…' : dirty ? 'Alterações ainda não salvas' : 'Sua lista permanece aberta ao fundo'}</span><div className="erp-window-actions">{actions}<button type="button" disabled={busy} onClick={requestClose}>Fechar</button></div></>}
    </footer>
  </dialog>
}
