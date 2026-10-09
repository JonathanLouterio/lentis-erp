import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'

type Props = { titleId: string; busy: boolean; onClose: () => void; children: ReactNode }
export default function CheckoutModal({ titleId, busy, onClose, children }: Props) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    dialog?.showModal()
    return () => dialog?.close()
  }, [])
  return <dialog ref={ref} className="erp-checkout-native-dialog" aria-labelledby={titleId} onCancel={(event) => {
    event.preventDefault()
    if (!busy) onClose()
  }}>{children}</dialog>
}
