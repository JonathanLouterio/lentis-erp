import { useCallback, useRef, useState } from 'react'
import UserManagement from './UserManagement'
import SystemSettings from './SystemSettings'
import './SystemSettings.css'

type Props = { onSavingChange: (value: boolean) => void; onDirtyChange: (value: boolean) => void; onConfigurationSaved: () => void }
export default function AdminWorkspace(props: Props) {
  const [section, setSection] = useState<'users' | 'settings'>('users')
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  function changeSection(next: typeof section) {
    if (saving || next === section) return
    if (dirty && !window.confirm('Descartar as alterações não salvas?')) return
    setDirty(false); props.onDirtyChange(false); setSection(next)
  }
  const callbacks = useRef(props)
  callbacks.current = props
  const handleSaving = useCallback((value: boolean) => { setSaving(value); callbacks.current.onSavingChange(value) }, [])
  const handleDirty = useCallback((value: boolean) => { setDirty(value); callbacks.current.onDirtyChange(value) }, [])
  const shared = { onSavingChange: handleSaving, onDirtyChange: handleDirty }
  return <div className="system-admin-workspace">
    <nav className="system-tabs" aria-label="Administração do sistema">
      <button type="button" aria-current={section === 'users' ? 'page' : undefined} disabled={saving} onClick={() => changeSection('users')}>Usuários e permissões</button>
      <button type="button" aria-current={section === 'settings' ? 'page' : undefined} disabled={saving} onClick={() => changeSection('settings')}>Configurações do sistema</button>
    </nav>
    {section === 'users' ? <UserManagement {...shared} /> : <SystemSettings {...shared} onSaved={props.onConfigurationSaved} />}
  </div>
}
