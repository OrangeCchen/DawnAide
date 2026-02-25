import { ref } from 'vue'
import type { Message } from '../types'

const WS_URL = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`

export const connected = ref(false)
let ws: WebSocket | null = null
let messageCallback: ((msg: Message) => void) | null = null
let heartbeatTimer: ReturnType<typeof setInterval> | null = null

export function onMessage(callback: (msg: Message) => void) {
  messageCallback = callback
}

export function connect() {
  if (ws && ws.readyState === WebSocket.OPEN) return

  ws = new WebSocket(WS_URL)

  ws.onopen = () => {
    connected.value = true
    console.log('[WS] Connected')
    if (heartbeatTimer) clearInterval(heartbeatTimer)
    heartbeatTimer = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'ping' }))
      }
    }, 30000)
  }

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.action === 'pong' || data.action === 'heartbeat') return
      if (messageCallback) {
        messageCallback(data as Message)
      }
    } catch (e) {
      console.error('[WS] Parse error:', e)
    }
  }

  ws.onclose = () => {
    connected.value = false
    if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null }
    console.log('[WS] Disconnected, reconnecting in 3s...')
    setTimeout(connect, 3000)
  }

  ws.onerror = (e) => {
    console.error('[WS] Error:', e)
  }
}

export function sendChat(message: string, teamId: string) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      action: 'chat',
      message,
      team_id: teamId,
    }))
  }
}
