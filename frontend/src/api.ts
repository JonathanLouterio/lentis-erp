export type ThemePreference = 'light' | 'dark' | 'system'

export type CurrentUser = {
  id: number
  username: string
  first_name: string
  last_name: string
  theme: ThemePreference
}

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers)
  headers.set('Accept', 'application/json')

  let response: Response

  try {
    response = await fetch(path, {
      ...options,
      headers,
      credentials: 'same-origin',
      cache: 'no-store',
    })
  } catch {
    throw new ApiError(
      'Não foi possível conectar. Verifique sua conexão e tente novamente.',
      0,
    )
  }

  const data = await response.json().catch(() => null)

  if (!response.ok) {
    const message =
      typeof data?.detail === 'string'
        ? data.detail
        : 'Não foi possível concluir a operação. Tente novamente.'

    throw new ApiError(message, response.status)
  }

  if (data === null) {
    throw new ApiError('O servidor retornou uma resposta inesperada.', 502)
  }

  return data as T
}

async function getCsrfToken(): Promise<string> {
  const data = await request<{ csrfToken: string }>('/api/auth/csrf/')
  return data.csrfToken
}

export function getCurrentUser(): Promise<CurrentUser> {
  return request<CurrentUser>('/api/me/')
}

export async function signIn(
  username: string,
  password: string,
): Promise<CurrentUser> {
  const token = await getCsrfToken()

  const data = await request<{
    user: CurrentUser
    csrfToken: string
  }>('/api/auth/login/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': token,
    },
    body: JSON.stringify({ username, password }),
  })

  return data.user
}

export async function signOut(): Promise<void> {
  const token = await getCsrfToken()

  await request('/api/auth/logout/', {
    method: 'POST',
    headers: {
      'X-CSRFToken': token,
    },
  })
}
export type AccessibleStore = {
  id: number
  code: string
  name: string
}

export function getMyStores(): Promise<AccessibleStore[]> {
  return request<AccessibleStore[]>('/api/me/stores/')
}
export async function updateTheme(
  theme: ThemePreference,
): Promise<{ theme: ThemePreference }> {
  const token = await getCsrfToken()

  return request<{ theme: ThemePreference }>('/api/me/preferences/', {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': token,
    },
    body: JSON.stringify({ theme }),
  })
}