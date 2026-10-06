import { useEffect } from 'react'
import type { ThemePreference } from '../api'

const STORAGE_KEY = 'lentis.theme'

function readStoredTheme(): ThemePreference {
  try {
    const value = localStorage.getItem(STORAGE_KEY)

    if (value === 'light' || value === 'dark' || value === 'system') {
      return value
    }
  } catch {
    // O tema continua funcionando se o navegador bloquear o armazenamento.
  }

  return 'system'
}

export function useTheme(accountTheme?: ThemePreference) {
  const preference = accountTheme ?? readStoredTheme()

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')

    function applyTheme() {
      const resolved =
        preference === 'system'
          ? media.matches
            ? 'dark'
            : 'light'
          : preference

      document.documentElement.dataset.theme = resolved
      document.documentElement.style.colorScheme = resolved
    }

    applyTheme()
    media.addEventListener('change', applyTheme)

    if (accountTheme) {
      try {
        localStorage.setItem(STORAGE_KEY, accountTheme)
      } catch {
        // A preferência permanece salva na conta.
      }
    }

    return () => {
      media.removeEventListener('change', applyTheme)
    }
  }, [accountTheme, preference])
}