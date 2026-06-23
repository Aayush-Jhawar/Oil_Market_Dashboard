import create from 'zustand'

import type { DashboardSnapshot } from '../types/snapshot'

type DashboardState = {
  snapshot: DashboardSnapshot | null
  setSnapshot: (s: DashboardSnapshot) => void
}

export const useDashboardStore = create<DashboardState>((set) => ({
  snapshot: null,
  setSnapshot: (data: any) => set((state) => {
    // Merge the incoming websocket payload into the state snapshot by type
    if (!state.snapshot) {
      if (data.type) {
        return { snapshot: { [data.type]: data.data, ts: data.timestamp } as any }
      }
      return { snapshot: data }
    }
    
    if (data.type) {
      return {
        snapshot: {
          ...state.snapshot,
          [data.type]: data.data,
          ts: data.timestamp || state.snapshot.ts
        } as any
      }
    }
    return { snapshot: data }
  }),
}))

// WebSocket connection helper
export function connectWebSocket(url?: string) {
  let wsUrl: string
  if (url) {
    // If the caller passed an http(s) base (e.g. http://localhost:8000), convert to ws(s)://host/ws
    if (url.startsWith('http://') || url.startsWith('https://')) {
      const stripped = url.replace(/^https?:\/\//, '').replace(/\/$/, '')
      wsUrl = (url.startsWith('https://') ? 'wss://' : 'ws://') + stripped + '/ws'
    } else {
      // assume it's already a ws:// or wss:// URL or a bare host
      wsUrl = url
    }
  } else {
    wsUrl = (location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + location.host + '/ws'
  }
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
