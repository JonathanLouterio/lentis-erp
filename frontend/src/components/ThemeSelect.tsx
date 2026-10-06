import { useState } from 'react'
import { updateTheme } from '../api'
import type { ThemePreference } from '../api'

type ThemeSelectProps = {
  value: ThemePreference
  disabled: boolean
  onSaved: (theme: ThemePreference) => void
}

export default function ThemeSelect({
  value,
  disabled,
  onSaved,
}: ThemeSelectProps) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function handleChange(next: string) {
    if (saving || disabled) return
    if (next !== 'light' && next !== 'dark' && next !== 'system') return

    setSaving(true)
    setError('')

    try {
      const result = await updateTheme(next)
      onSaved(result.theme)
    } catch {
      setError('Não foi possível salvar o tema. Tente novamente.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="erp-theme-control">
      <div className="erp-theme-field">
        <label htmlFor="theme-preference">Tema</label>

        <select
          id="theme-preference"
          value={value}
          disabled={disabled || saving}
          onChange={(event) => void handleChange(event.target.value)}
          aria-describedby={error ? 'theme-error' : undefined}
          aria-busy={saving}
        >
          <option value="light">Claro</option>
          <option value="dark">Escuro</option>
          <option value="system">Automático</option>
        </select>

        {saving && <span role="status">Salvando…</span>}
      </div>

      {error && (
        <p id="theme-error" className="erp-theme-error" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}