import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError, getCurrentUser, signIn, signOut } from './api'
import type { CurrentUser, ThemePreference } from './api'
import AppLayout from './components/AppLayout'
import { useTheme } from './hooks/useTheme'
import './App.css'
import './themes.css'

function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : 'Ocorreu um erro inesperado. Tente novamente.'
}

export default function App() {
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [checkingSession, setCheckingSession] = useState(true)
  const [sessionError, setSessionError] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useTheme(user?.theme)

  function handleThemeSaved(theme: ThemePreference, userId: number) {
    setUser((current) =>
      current?.id === userId ? { ...current, theme } : current,
    )
  }

  useEffect(() => {
    let ignore = false

    async function loadSession() {
      try {
        const currentUser = await getCurrentUser()
        if (!ignore) setUser(currentUser)
      } catch (err) {
        if (ignore) return
        if (!(err instanceof ApiError && [401, 403].includes(err.status))) {
          setSessionError(errorMessage(err))
        }
      } finally {
        if (!ignore) setCheckingSession(false)
      }
    }

    void loadSession()
    return () => {
      ignore = true
    }
  }, [])

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    setError('')
    setBusy(true)
    try {
      const currentUser = await signIn(username.trim(), password)
      setUser(currentUser)
      setShowPassword(false)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setPassword('')
      setBusy(false)
    }
  }

  async function handleLogout() {
    if (busy) return
    setError('')
    setBusy(true)
    try {
      await signOut()
      setUser(null)
      setPassword('')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  if (user && !checkingSession) {
    return (
      <AppLayout
        key={user.id}
        user={user}
        busy={busy}
        error={error}
        onLogout={handleLogout}
        onThemeSaved={(theme) => handleThemeSaved(theme, user.id)}
      />
    )
  }

  return (
    <main className="login-layout">
      <section className="brand-panel" aria-label="Lentis ERP">
        <div className="brand-content">
          <div className="brand-name" aria-label="Lentis">
            <span>LENTIS</span>
            <svg className="brand-glasses" viewBox="0 0 72 40" fill="none" aria-hidden="true">
              <circle cx="19" cy="22" r="13" stroke="currentColor" strokeWidth="7" />
              <circle cx="53" cy="22" r="13" stroke="currentColor" strokeWidth="7" />
              <path d="M32 21 Q36 16 40 21" stroke="currentColor" strokeWidth="7" strokeLinecap="round" />
            </svg>
          </div>
          <div className="brand-product">ERP</div>
          <p>Gestão inteligente para óticas.</p>
        </div>
        <span className="brand-caption">Sua ótica sob uma nova visão.</span>
      </section>

      <section className="access-panel" aria-label="Acesso ao sistema">
        <div className="access-content">
          {checkingSession ? (
            <p className="session-status" role="status">Verificando sua sessão…</p>
          ) : sessionError ? (
            <div className="session-card">
              <h1>Não foi possível carregar</h1>
              <p className="error-message" role="alert">{sessionError}</p>
              <button type="button" className="primary-button" onClick={() => window.location.reload()}>
                Tentar novamente
              </button>
            </div>
          ) : (
            <>
              <header className="login-heading">
                <span className="eyebrow">BEM-VINDO AO LENTIS</span>
                <h1>Bem-vindo de volta</h1>
                <p className="intro-text">Entre com suas credenciais para acessar o sistema.</p>
              </header>
              <form onSubmit={handleLogin} aria-busy={busy}>
                <div className="form-field">
                  <label htmlFor="username">Usuário</label>
                  <input
                    id="username" name="username" type="text" autoComplete="username"
                    placeholder="Seu usuário" value={username}
                    onChange={(event) => setUsername(event.target.value)} required disabled={busy}
                  />
                </div>
                <div className="form-field">
                  <label htmlFor="password">Senha</label>
                  <div className="password-field">
                    <input
                      id="password" name="password" type={showPassword ? 'text' : 'password'}
                      autoComplete="current-password" placeholder="Sua senha" value={password}
                      onChange={(event) => setPassword(event.target.value)} required disabled={busy}
                    />
                    <button
                      className="password-toggle" type="button"
                      aria-label={showPassword ? 'Ocultar senha' : 'Mostrar senha'}
                      aria-controls="password" aria-pressed={showPassword}
                      onClick={() => setShowPassword((visible) => !visible)} disabled={busy}
                    >
                      {showPassword ? 'Ocultar' : 'Mostrar'}
                    </button>
                  </div>
                </div>
                {error && <p className="error-message" role="alert">{error}</p>}
                <button className="primary-button" type="submit" disabled={busy}>
                  {busy ? 'Entrando…' : 'Entrar'}
                </button>
              </form>
              <footer className="login-footer">
                <span>Lentis ERP</span>
                <span>Gestão inteligente para óticas</span>
              </footer>
            </>
          )}
        </div>
      </section>
    </main>
  )
}
