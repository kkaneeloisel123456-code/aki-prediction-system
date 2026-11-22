import { computed, ref } from 'vue'
import { api } from '../api/client'
import type { AuthUser } from '../api/types'

const user = ref<AuthUser | null>(null)
const configured = ref(true)
const ready = ref(false)
const statusError = ref(false)
let restoring: Promise<void> | null = null

async function restore(force = false): Promise<void> {
  if (ready.value && !force) return
  if (restoring) return restoring
  restoring = api.authStatus()
    .then((status) => {
      user.value = status.authenticated ? status.user : null
      configured.value = status.configured
      statusError.value = false
    })
    .catch(() => {
      user.value = null
      statusError.value = true
    })
    .finally(() => {
      ready.value = true
      restoring = null
    })
  return restoring
}

async function login(username: string, password: string, remember: boolean) {
  const status = await api.login(username, password, remember)
  user.value = status.user
  configured.value = status.configured
  statusError.value = false
  ready.value = true
  return status
}

async function logout() {
  try {
    await api.logout()
  } finally {
    user.value = null
    ready.value = true
  }
}

function clearSession() {
  user.value = null
  ready.value = true
}

if (typeof window !== 'undefined') {
  window.addEventListener('aki:unauthorized', clearSession)
}

export function useAuth() {
  return {
    user,
    configured,
    ready,
    statusError,
    isAuthenticated: computed(() => user.value !== null),
    restore,
    login,
    logout,
    clearSession,
  }
}
