import { useState, useCallback } from 'react'

const STORAGE_KEY = 'app_auth_token'

export function useAuth() {
  const [password, setPassword] = useState(() => {
    if (typeof window === 'undefined') return ''
    return localStorage.getItem(STORAGE_KEY) || ''
  })

  const login = useCallback((pwd) => {
    localStorage.setItem(STORAGE_KEY, pwd)
    setPassword(pwd)
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY)
    setPassword('')
  }, [])

  const authHeaders = password ? { 'x-webhook-password': password } : {}

  return { password, login, logout, authHeaders }
}