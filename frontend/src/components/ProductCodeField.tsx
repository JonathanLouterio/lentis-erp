import { useEffect, useEffectEvent, useId, useRef, useState } from 'react'
import type { Ref } from 'react'
import type { IScannerControls } from '@zxing/browser'
import './ProductCodeField.css'

const CODE_LIMIT = 30

export function readProductCode(raw: string) {
  const code = raw.trim()
  const characters = Array.from(code)
  const hasControlCharacter = characters.some(char => {
    const point = char.charCodeAt(0)
    return point < 32 || point === 127
  })
  return code && characters.length <= CODE_LIMIT && !hasControlCharacter ? code : null
}

type ScanButtonProps = {
  scanning: boolean
  disabled?: boolean
  cameraId: string
  onToggle: () => void
  ref?: Ref<HTMLButtonElement>
}

export function CodeScanButton({ scanning, disabled, cameraId, onToggle, ref }: ScanButtonProps) {
  const expanded = scanning && !disabled
  return (
    <button type="button" className="product-code-scan" ref={ref} disabled={disabled}
      aria-label={expanded ? 'Fechar câmera' : 'Ler com câmera'}
      title={expanded ? 'Fechar câmera' : 'Ler código de barras ou QR Code'}
      aria-expanded={expanded} aria-controls={expanded ? cameraId : undefined} onClick={onToggle}>
      <svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
        <path d={expanded ? 'm6 6 12 12M18 6 6 18' : 'M8 4H4v4m12-4h4v4m0 8v4h-4m-8 0H4v-4M7.5 8v8m3-8v8m3-8v8m3-8v8'} />
      </svg>
    </button>
  )
}

function cameraError(error: unknown) {
  const name = error instanceof Error ? error.name : ''
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return 'A câmera não foi autorizada. Libere o acesso no navegador ou digite o código.'
  }
  if (name === 'NotFoundError') return 'Nenhuma câmera foi encontrada. Digite o código ou use um leitor externo.'
  return 'Não foi possível iniciar a câmera. Verifique se ela está livre ou digite o código.'
}

export function CodeCamera({ onCode, onError }: { onCode: (value: string) => void; onError: (message: string) => void }) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [ready, setReady] = useState(false)
  const receive = useEffectEvent(onCode)
  const fail = useEffectEvent(onError)

  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    let closed = false
    let delivered = false
    let stream: MediaStream | undefined
    let controls: IScannerControls | undefined
    const stopTracks = (source?: MediaStream) => source?.getTracks().forEach(track => track.stop())

    async function start(preview: HTMLVideoElement) {
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
        fail('A câmera precisa de HTTPS e de um navegador compatível. Você também pode digitar o código.')
        return
      }
      try {
        const [{ BrowserMultiFormatReader }, { BarcodeFormat, DecodeHintType }] = await Promise.all([
          import('@zxing/browser'),
          import('@zxing/library'),
        ])
        if (closed) return
        stream = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: { facingMode: { ideal: 'environment' } },
        })
        if (closed) {
          stopTracks(stream)
          return
        }
        stream.getVideoTracks().forEach(track => track.addEventListener('ended', () => {
          if (!closed && !delivered) fail('A câmera foi desconectada. Tente novamente ou digite o código.')
        }, { once: true }))
        // UPC-A and EAN-13 with a leading zero have the same bars. Prefer the 13-digit form.
        const scanner = new BrowserMultiFormatReader(new Map([[DecodeHintType.POSSIBLE_FORMATS, [
          BarcodeFormat.EAN_13, BarcodeFormat.EAN_8, BarcodeFormat.UPC_E, BarcodeFormat.CODE_128,
          BarcodeFormat.CODE_39, BarcodeFormat.CODE_93, BarcodeFormat.ITF, BarcodeFormat.CODABAR, BarcodeFormat.QR_CODE,
        ]]]))
        controls = await scanner.decodeFromStream(stream, preview, (result) => {
          if (closed || delivered || !result) return
          delivered = true
          receive(result.getText())
        })
        if (closed || delivered) controls.stop()
        else setReady(true)
      } catch (error) {
        if (!closed) fail(cameraError(error))
      }
    }

    void start(video)
    return () => {
      closed = true
      controls?.stop()
      stopTracks(stream)
      video.srcObject = null
    }
  }, [])

  return (
    <div className="product-code-camera">
      <p role="status">{ready ? 'Posicione o código de barras ou QR Code no centro da câmera.' : 'Abrindo câmera… Se o navegador pedir, permita o acesso.'}</p>
      <video ref={videoRef} aria-label="Prévia da câmera" autoPlay muted playsInline />
    </div>
  )
}

export default function ProductCodeField({ value, disabled, onChange }: { value: string; disabled: boolean; onChange: (value: string) => void }) {
  const fieldId = useId()
  const fieldRef = useRef<HTMLInputElement>(null)
  const [scanning, setScanning] = useState(false)
  const [feedback, setFeedback] = useState<{ text: string; error: boolean } | null>(null)

  if (disabled && scanning) setScanning(false)

  function finish(text: string, error: boolean) {
    setScanning(false)
    setFeedback({ text, error })
    fieldRef.current?.focus()
  }

  function acceptCode(raw: string) {
    const code = readProductCode(raw)
    if (!code) {
      finish('Use um código de produto em uma única linha, com até 30 caracteres. O campo foi mantido.', true)
      return
    }
    onChange(code)
    finish('Código lido. Salve o produto para confirmar.', false)
  }

  return (
    <div className="product-code-field">
      <label htmlFor={fieldId}>Código de barras ou QR Code</label>
      <div className="product-code-controls">
        <input id={fieldId} ref={fieldRef} type="text" value={value} autoComplete="off" autoCapitalize="off" spellCheck={false}
          onChange={event => { setFeedback(null); onChange(event.target.value) }}
          onKeyDown={event => {
            // Keyboard-style readers often send Enter after the code. Saving remains explicit.
            if (event.key === 'Enter') event.preventDefault()
          }} />
        <CodeScanButton scanning={scanning} disabled={disabled} cameraId={`${fieldId}-camera`} onToggle={() => {
          setFeedback(null)
          setScanning(current => !current)
        }} />
      </div>
      {scanning && !disabled && <div id={`${fieldId}-camera`}>
        <CodeCamera onCode={acceptCode} onError={message => finish(message, true)} />
      </div>}
      {feedback && <p className="product-code-feedback" role={feedback.error ? 'alert' : 'status'}>{feedback.text}</p>}
    </div>
  )
}
