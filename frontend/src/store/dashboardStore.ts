import create from 'zustand'

import type { DashboardSnapshot } from '../types/snapshot'

type DashboardState = {
  snapshot: DashboardSnapshot | null
  setSnapshot: (s: DashboardSnapshot) => void
}

export const useDashboardStore = create<DashboardState>((set) => ({
  snapshot: null,
  setSnapshot: (s: DashboardSnapshot) => set({ snapshot: s }),
}))

// WebSocket connection helper
export function connectWebSocket(url?: string) {
  const wsUrl = url ?? (location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + location.host + '/ws'
  let socket: WebSocket | null = null
  let backoff = 2000

  function open() {
    socket = new WebSocket(wsUrl)
    socket.onopen = () => {
      backoff = 2000
      console.info('WS connected', wsUrl)
    }
    socket.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data)
        useDashboardStore.getState().setSnapshot(data)
      } catch (e) {
        console.error('WS parse error', e)
      }
    }
    socket.onclose = () => {
      console.warn('WS closed — reconnecting in', backoff)
      setTimeout(open, backoff)
      backoff = Math.min(16000, backoff * 2)
    }
    socket.onerror = (e) => {
      console.error('WS error', e)
      socket?.close()
    }
  }

  open()

  return {
    close: () => socket?.close(),
  }
}
