import { useEffect, useRef, useState } from 'react'
import './MyProfile.css'

type Props = {
  name: string; username: string; role: string; avatar: string | null; collapsed: boolean; disabled: boolean
  onOpen: (tab: 'details' | 'preferences') => void; onLogout: () => void
}
export default function ProfileMenu({ name, username, role, avatar, collapsed, disabled, onOpen, onLogout }: Props) {
  const [open, setOpen] = useState(false), [failedAvatar, setFailedAvatar] = useState('')
  const root = useRef<HTMLDivElement>(null), trigger = useRef<HTMLButtonElement>(null)
  const initials = name.split(/\s+/).slice(0, 2).map(part => part[0]).join('').toUpperCase()
  useEffect(() => {
    if (!open) return
    root.current?.querySelector<HTMLButtonElement>('[role=menuitem]')?.focus()
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false) }
    document.addEventListener('pointerdown', outside)
    return () => document.removeEventListener('pointerdown', outside)
  }, [open])
  function choose(action: () => void) { setOpen(false); trigger.current?.focus(); action() }
  return <div ref={root} className={`personal-menu${collapsed ? ' is-collapsed' : ''}`}>
    {open && <div className="personal-menu-popover" role="menu" aria-label="Conta do usuário" onKeyDown={event => {
      const items = [...event.currentTarget.querySelectorAll<HTMLButtonElement>('[role=menuitem]')]
      const current = items.indexOf(document.activeElement as HTMLButtonElement)
      if (event.key === 'Escape') { event.preventDefault(); setOpen(false); trigger.current?.focus() }
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); items[(current + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]?.focus() }
      if (event.key === 'Tab') setOpen(false)
    }}>
      <span className="personal-menu-caption">MINHA CONTA</span>
      <button type="button" role="menuitem" disabled={disabled} onClick={() => choose(() => onOpen('details'))}>Meu perfil <span aria-hidden="true">↗</span></button>
      <button type="button" role="menuitem" disabled={disabled} onClick={() => choose(() => onOpen('preferences'))}>Preferências <span aria-hidden="true">◐</span></button>
      <button type="button" role="menuitem" disabled={disabled} onClick={() => choose(onLogout)}>Sair da conta <span aria-hidden="true">↪</span></button>
    </div>}
    <button ref={trigger} type="button" className="personal-menu-trigger" disabled={disabled} aria-haspopup="menu" aria-expanded={open} aria-label={`Abrir menu do usuário ${name}`} title={collapsed ? 'Meu perfil e preferências' : undefined}
      onClick={() => setOpen(value => !value)} onKeyDown={event => { if (event.key === 'ArrowUp' || event.key === 'ArrowDown') { event.preventDefault(); setOpen(true) } }}>
      <span className="personal-avatar">{avatar && failedAvatar !== avatar ? <img src={avatar} alt="" onError={() => setFailedAvatar(avatar)} /> : initials}</span>
      {!collapsed && <><span className="personal-menu-identity"><strong>{name}</strong><span>@{username}</span><small>{role}</small></span><span className="personal-menu-chevron" aria-hidden="true">⌃</span></>}
    </button>
  </div>
}
