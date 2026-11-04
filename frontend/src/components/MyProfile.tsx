import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError, getMyProfile, saveMyProfile } from '../api'
import type { MyProfile as ProfileData, ProfilePayload, ThemePreference } from '../api'
import FormDialog from './FormDialog'
import ThemeSelect from './ThemeSelect'
import './MyProfile.css'

type Details = Pick<ProfileData, 'first_name' | 'last_name' | 'email' | 'phone' | 'whatsapp' | 'job_title' | 'bio'>
type Props = {
  userId: number; initialTab: 'details' | 'preferences'; theme: ThemePreference
  onThemeSaved: (theme: ThemePreference) => void; onLoaded: (profile: ProfileData) => void
  onSavingChange: (value: boolean) => void; onDirtyChange: (value: boolean) => void
}
const message = (error: unknown) => error instanceof Error ? error.message : 'Não foi possível concluir a operação.'
function details(profile: ProfileData): Details { return { first_name: profile.first_name, last_name: profile.last_name, email: profile.email, phone: profile.phone, whatsapp: profile.whatsapp, job_title: profile.job_title, bio: profile.bio } }
const empty: Details = { first_name: '', last_name: '', email: '', phone: '', whatsapp: '', job_title: '', bio: '' }

export default function MyProfile({ userId, initialTab, theme, onThemeSaved, onLoaded, onSavingChange, onDirtyChange }: Props) {
  const [profile, setProfile] = useState<ProfileData | null>(null), [tab, setTab] = useState(initialTab)
  const [loading, setLoading] = useState(true), [loadError, setLoadError] = useState(''), [reload, setReload] = useState(0)
  const [editing, setEditing] = useState(false), [form, setForm] = useState<Details>(empty)
  const [photo, setPhoto] = useState<File | null>(null), [removeAvatar, setRemoveAvatar] = useState(false), [preview, setPreview] = useState('')
  const [saving, setSaving] = useState(false), [error, setError] = useState(''), [success, setSuccess] = useState(''), [conflict, setConflict] = useState(false)
  const [failedAvatar, setFailedAvatar] = useState('')
  const upload = useRef<HTMLInputElement>(null), sending = useRef(false)
  const callbacks = useRef({ onLoaded, onSavingChange, onDirtyChange }); callbacks.current = { onLoaded, onSavingChange, onDirtyChange }
  const dirty = editing && !!profile && (JSON.stringify(form) !== JSON.stringify(details(profile)) || photo !== null || removeAvatar)
  useEffect(() => { setTab(initialTab) }, [initialTab])
  useEffect(() => { callbacks.current.onDirtyChange(dirty) }, [dirty])
  useEffect(() => () => { callbacks.current.onDirtyChange(false); callbacks.current.onSavingChange(false) }, [])
  useEffect(() => {
    if (!photo) { setPreview(''); return }
    const url = URL.createObjectURL(photo); setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [photo])
  useEffect(() => {
    let ignore = false
    setLoading(true); setLoadError('')
    void getMyProfile().then(result => { if (!ignore) { setProfile(result); callbacks.current.onLoaded(result) } })
      .catch(err => { if (!ignore) { setLoadError(message(err)); setProfile(null) } })
      .finally(() => { if (!ignore) setLoading(false) })
    return () => { ignore = true }
  }, [userId, reload])
  function openEditor() {
    if (!profile || loading) return
    setForm(details(profile)); setPhoto(null); setRemoveAvatar(false); setError(''); setSuccess(''); setConflict(false); setEditing(true)
  }
  function closeEditor() { if (!sending.current) { setEditing(false); setPhoto(null); setRemoveAvatar(false); setError('') } }
  function change<K extends keyof Details>(key: K, value: Details[K]) { setForm(current => ({ ...current, [key]: value })); setError('') }
  function choosePhoto(file?: File) {
    if (!file) return
    if (file.size > 5 * 1024 * 1024) { setError('Escolha uma foto de até 5 MB.'); return }
    if (file.type && !['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) { setError('Escolha uma foto JPG, PNG ou WebP.'); return }
    setPhoto(file); setRemoveAvatar(false); setError('')
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!profile || sending.current || conflict) return
    if (!event.currentTarget.reportValidity()) return
    sending.current = true; setSaving(true); callbacks.current.onSavingChange(true); setError('')
    try {
      const payload: ProfilePayload = { ...form, version: profile.version, remove_avatar: removeAvatar, ...(photo ? { photo } : {}) }
      const result = await saveMyProfile(payload)
      setProfile(result); callbacks.current.onLoaded(result); setEditing(false); setPhoto(null); setRemoveAvatar(false); setSuccess('Seu perfil foi atualizado.')
    } catch (err) { setError(message(err)); if (err instanceof ApiError && [403, 409].includes(err.status)) setConflict(true) }
    finally { sending.current = false; setSaving(false); callbacks.current.onSavingChange(false) }
  }
  const name = profile ? [profile.first_name, profile.last_name].filter(Boolean).join(' ') || profile.username : ''
  const initials = name.split(/\s+/).slice(0, 2).map(part => part[0]).join('').toUpperCase()
  const avatar = editing ? removeAvatar ? null : preview || profile?.avatar_url : profile?.avatar_url
  function avatarView(edit = false) { return <div className={`personal-photo${edit ? ' is-editor' : ''}`}>{avatar && failedAvatar !== avatar ? <img src={avatar} alt={edit ? 'Prévia da foto de perfil' : 'Sua foto de perfil'} onError={() => setFailedAvatar(avatar)} /> : <span aria-hidden="true">{initials || 'U'}</span>}</div> }
  return <section className="my-profile-page">
    <header className="personal-heading"><div><span className="personal-eyebrow">MINHA CONTA</span><h1>Meu perfil</h1><p>Seus dados, sua foto e suas preferências.</p></div><div className="personal-actions"><button type="button" disabled={loading || saving} onClick={() => setReload(value => value + 1)}>Atualizar</button>{tab === 'details' && <button className="personal-primary" type="button" disabled={loading || !profile || !!loadError} onClick={openEditor}>Editar perfil</button>}</div></header>
    <nav className="personal-tabs" aria-label="Seções do perfil"><button type="button" aria-current={tab === 'details' ? 'page' : undefined} onClick={() => setTab('details')}>Dados pessoais</button><button type="button" aria-current={tab === 'preferences' ? 'page' : undefined} onClick={() => setTab('preferences')}>Preferências</button></nav>
    {success && <p className="personal-success" role="status">{success}</p>}
    {loading ? <p role="status">Carregando seu perfil…</p> : loadError ? <p className="personal-error" role="alert">{loadError} Use Atualizar para tentar novamente.</p> : profile && <div className="personal-grid">
      <aside className="personal-card personal-summary">{avatarView()}<h2>{name}</h2><p>@{profile.username}</p>{profile.job_title && <strong>{profile.job_title}</strong>}<span className="personal-private">Perfil pessoal</span><p className="personal-muted">Suas informações de apresentação e contato.</p></aside>
      {tab === 'details' ? <article className="personal-card"><div className="personal-card-heading"><h2>Dados pessoais</h2><span>Minha conta</span></div><dl className="personal-details">{Object.entries({ 'Nome': profile.first_name, 'Sobrenome': profile.last_name, 'E-mail de contato': profile.email, 'Telefone': profile.phone, 'WhatsApp': profile.whatsapp, 'Cargo / apresentação': profile.job_title }).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value || 'Não informado'}</dd></div>)}<div className="personal-full"><dt>Sobre mim</dt><dd className="personal-bio">{profile.bio || 'Conte um pouco sobre você no seu perfil.'}</dd></div></dl></article> : <article className="personal-card"><div className="personal-card-heading"><h2>Preferências de aparência</h2></div><p className="personal-muted">Escolha como deseja visualizar o Lentis neste e nos próximos acessos.</p><ThemeSelect value={theme} disabled={saving} onSaved={onThemeSaved} /><div className="personal-theme-hint"><strong>Automático</strong><p>Acompanha o tema claro ou escuro configurado no seu dispositivo.</p></div></article>}
    </div>}
    {editing && profile && <FormDialog title="Editar meu perfil" sectionLabel="MINHA CONTA" subtitle="Atualize suas informações e escolha sua foto." busy={saving} dirty={dirty} notice={error} onClose={closeEditor} actions={<button type="submit" form="personal-profile-form" className="erp-action-button" disabled={saving || conflict}>{saving ? 'Salvando…' : 'Salvar perfil'}</button>}>
      <div className="my-profile-page personal-editor">
        {error && <p className="personal-error" role="alert">{error}{conflict && ' Feche a janela e clique em Atualizar.'}</p>}
        <form id="personal-profile-form" onSubmit={save} noValidate><fieldset disabled={saving || conflict}>
          <legend className="personal-sr-only">Dados e foto de perfil</legend>
          <div className="personal-photo-editor">{avatarView(true)}<div><strong>Foto do perfil</strong><p className="personal-muted">JPG, PNG ou WebP, até 5 MB e 16 megapixels. Recorte central quadrado.</p><div className="personal-actions"><button type="button" onClick={() => upload.current?.click()}>Escolher foto</button>{(photo || profile.avatar_url) && !removeAvatar && <button type="button" onClick={() => { setPhoto(null); setRemoveAvatar(true); setError('') }}>Remover foto</button>}{(photo || removeAvatar) && <button type="button" onClick={() => { setPhoto(null); setRemoveAvatar(false) }}>Desfazer alteração da foto</button>}</div><input ref={upload} className="personal-sr-only" type="file" accept="image/jpeg,image/png,image/webp" aria-label="Arquivo da foto de perfil" onChange={event => { choosePhoto(event.target.files?.[0]); event.target.value = '' }} />{removeAvatar && <p className="personal-muted">A foto será removida ao salvar.</p>}</div></div>
          <div className="personal-fields">
            <label>Nome<input autoComplete="given-name" maxLength={150} value={form.first_name} onChange={event => change('first_name', event.target.value)} /></label>
            <label>Sobrenome<input autoComplete="family-name" maxLength={150} value={form.last_name} onChange={event => change('last_name', event.target.value)} /></label>
            <div className="personal-field personal-full"><label htmlFor="personal-email">E-mail de contato</label><input id="personal-email" aria-describedby="personal-email-help" type="email" autoComplete="email" maxLength={254} value={form.email} onChange={event => change('email', event.target.value)} /><small id="personal-email-help">Seu usuário de acesso continua sendo @{profile.username}.</small></div>
            <label>Telefone<input type="tel" autoComplete="tel" maxLength={20} placeholder="(41) 99999-9999" value={form.phone} onChange={event => change('phone', event.target.value)} /></label>
            <label>WhatsApp<input type="tel" maxLength={20} placeholder="+55 41 99999-9999" value={form.whatsapp} onChange={event => change('whatsapp', event.target.value)} /></label>
            <div className="personal-field personal-full"><label htmlFor="personal-job-title">Cargo / apresentação</label><input id="personal-job-title" aria-describedby="personal-job-help" maxLength={80} placeholder="Ex.: Atendimento ao cliente" value={form.job_title} onChange={event => change('job_title', event.target.value)} /><small id="personal-job-help">Descrição pessoal. As permissões e os vínculos são definidos pelo administrador.</small></div>
            <div className="personal-field personal-full"><label htmlFor="personal-bio">Sobre mim</label><textarea id="personal-bio" aria-describedby="personal-bio-count" rows={4} maxLength={500} value={form.bio} onChange={event => change('bio', event.target.value)} /><small id="personal-bio-count">{form.bio.length}/500 caracteres</small></div>
          </div>
        </fieldset></form>
      </div>
    </FormDialog>}
  </section>
}
