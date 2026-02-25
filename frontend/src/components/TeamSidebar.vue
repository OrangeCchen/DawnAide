<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useTeamStore } from '../stores/teamStore'

const store = useTeamStore()

// iMessage Bot 状态: 'off' | 'standby' | 'active'
const botStatus = ref<'off' | 'standby' | 'active'>('off')
const botLoading = ref(false)

const botStatusLabel = computed(() => {
  if (botLoading.value) return '...'
  if (botStatus.value === 'active') return '活跃'
  if (botStatus.value === 'standby') return '待命'
  return 'OFF'
})

const botStatusIcon = computed(() => {
  if (botStatus.value === 'active') return '🟢'
  if (botStatus.value === 'standby') return '🟡'
  return '⚪'
})

async function fetchBotStatus() {
  try {
    const res = await fetch('/api/imessage-bot/status')
    const data = await res.json()
    botStatus.value = data.status || 'off'
  } catch { /* ignore */ }
}

async function toggleBot() {
  botLoading.value = true
  try {
    if (botStatus.value === 'active') {
      const res = await fetch('/api/imessage-bot/stop', { method: 'POST' })
      if (res.ok) {
        const data = await res.json()
        botStatus.value = data.status || 'standby'
      }
    } else {
      const res = await fetch('/api/imessage-bot/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      if (res.ok) {
        const data = await res.json()
        botStatus.value = data.status || 'active'
      }
    }
  } catch { /* ignore */ }
  botLoading.value = false
}

onMounted(fetchBotStatus)

async function createConversation() {
  const now = new Date()
  const timeLabel = `${now.getMonth() + 1}/${now.getDate()} ${now.getHours()}:${String(now.getMinutes()).padStart(2, '0')}`
  await store.createTeam(`新对话 ${timeLabel}`)
}

async function handleDelete(e: Event, teamId: string) {
  e.stopPropagation()
  await store.deleteTeam(teamId)
}

function getConversationIcon(idx: number): string {
  const icons = ['💬', '🗨️', '📝', '🔍', '💡', '📊', '🚀', '⚡', '🎯', '✨']
  return icons[idx % icons.length]
}

function formatTime(timestamp: string): string {
  if (!timestamp) return ''
  const d = new Date(timestamp)
  const now = new Date()
  const isToday = d.toDateString() === now.toDateString()
  if (isToday) {
    return `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
  }
  return `${d.getMonth() + 1}/${d.getDate()}`
}
</script>

<template>
  <div class="sidebar-root">
    <!-- 标题 -->
    <div class="sidebar-header">
      <span class="sidebar-title">对话</span>
      <button @click="createConversation" class="btn-add" title="新建对话">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path d="M8 3v10M3 8h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
      </button>
    </div>

    <!-- 对话列表 -->
    <div class="team-list">
      <div
        v-for="(team, idx) in store.teams"
        :key="team.id"
        @click="store.selectTeam(team.id)"
        class="team-item"
        :class="{ active: store.currentTeamId === team.id }"
      >
        <span class="team-icon">{{ getConversationIcon(idx) }}</span>
        <div class="team-info">
          <span class="team-name">{{ team.name }}</span>
          <span class="team-time">{{ formatTime(team.created_at) }}</span>
        </div>
        <button
          @click="(e: MouseEvent) => handleDelete(e, team.id)"
          class="btn-delete"
          title="删除"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M4 4l6 6M10 4l-6 6" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
          </svg>
        </button>
      </div>

      <!-- 空状态 -->
      <div v-if="store.teams.length === 0" class="empty-state">
        <p class="empty-text">暂无对话</p>
        <p class="empty-hint">点击 + 开始新对话</p>
      </div>
    </div>

    <!-- 专家模式开关 -->
    <div class="expert-section">
      <button
        @click="store.toggleExpertMode()"
        class="expert-toggle"
        :class="{ 'expert-active': store.expertMode }"
        :title="store.expertMode ? '专家模式已开启：多Agent协作分析' : '点击开启专家模式'"
      >
        <span class="expert-icon">{{ store.expertMode ? '🧠' : '💬' }}</span>
        <span class="expert-label">专家模式</span>
        <span class="expert-status-badge">{{ store.expertMode ? '开启' : '关闭' }}</span>
      </button>
    </div>

    <!-- iMessage Bot 开关 -->
    <div class="bot-section">
      <button
        @click="toggleBot"
        class="bot-toggle"
        :class="{ 'bot-active': botStatus === 'active', 'bot-standby': botStatus === 'standby' }"
        :disabled="botLoading"
      >
        <span class="bot-icon">{{ botStatusIcon }}</span>
        <span class="bot-label">iMessage Bot</span>
        <span class="bot-status-badge">{{ botStatusLabel }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.sidebar-root {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border);
}

.sidebar-header {
  padding: 16px 20px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sidebar-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.btn-add {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.btn-add:hover {
  background: var(--bg-hover);
  color: var(--accent);
}

.team-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 12px;
}

.team-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.15s;
  margin-bottom: 2px;
}

.team-item:hover {
  background: var(--bg-hover);
}

.team-item.active {
  background: var(--bg-active);
}

.team-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.team-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.team-name {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 400;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.team-time {
  font-size: 11px;
  color: var(--text-light);
}

.team-item.active .team-name {
  color: var(--accent);
  font-weight: 500;
}

.btn-delete {
  width: 22px;
  height: 22px;
  border-radius: var(--radius-sm);
  border: none;
  background: transparent;
  color: var(--text-light);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  opacity: 0;
  transition: all 0.15s;
}

.team-item:hover .btn-delete {
  opacity: 1;
}

.btn-delete:hover {
  background: rgba(255, 59, 48, 0.1);
  color: #FF3B30;
}

.empty-state {
  padding: 32px 16px;
  text-align: center;
}

.empty-text {
  font-size: 14px;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.empty-hint {
  font-size: 12px;
  color: var(--text-light);
}

/* 专家模式开关 */
.expert-section {
  padding: 12px 12px 0;
  flex-shrink: 0;
}

.expert-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--bg-card);
  cursor: pointer;
  transition: all 0.2s;
}

.expert-toggle:hover {
  background: var(--bg-hover);
}

.expert-toggle.expert-active {
  border-color: rgba(0, 122, 255, 0.4);
  background: rgba(0, 122, 255, 0.05);
}

.expert-icon {
  font-size: 13px;
  flex-shrink: 0;
}

.expert-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  flex: 1;
  text-align: left;
}

.expert-status-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 10px;
  background: var(--bg-secondary);
  color: var(--text-light);
  flex-shrink: 0;
}

.expert-active .expert-status-badge {
  background: rgba(0, 122, 255, 0.12);
  color: var(--accent);
}

/* iMessage Bot */
.bot-section {
  padding: 12px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.bot-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--bg-card);
  cursor: pointer;
  transition: all 0.2s;
}

.bot-toggle:hover {
  background: var(--bg-hover);
}

.bot-toggle.bot-active {
  border-color: rgba(52, 199, 89, 0.4);
  background: rgba(52, 199, 89, 0.05);
}

.bot-toggle.bot-standby {
  border-color: rgba(255, 204, 0, 0.4);
  background: rgba(255, 204, 0, 0.05);
}

.bot-toggle:disabled {
  opacity: 0.6;
  cursor: wait;
}

.bot-icon {
  font-size: 10px;
  flex-shrink: 0;
}

.bot-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  flex: 1;
  text-align: left;
}

.bot-status-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 10px;
  background: var(--bg-secondary);
  color: var(--text-light);
  flex-shrink: 0;
}

.bot-active .bot-status-badge {
  background: rgba(52, 199, 89, 0.15);
  color: var(--accent-green);
}

.bot-standby .bot-status-badge {
  background: rgba(255, 204, 0, 0.15);
  color: #cc9900;
}
</style>
