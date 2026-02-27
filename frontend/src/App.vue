<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useTeamStore } from './stores/teamStore'
import { connect, onMessage } from './api/websocket'
import TeamSidebar from './components/TeamSidebar.vue'
import MemberPanel from './components/MemberPanel.vue'
import ChatArea from './components/ChatArea.vue'
import KnowledgeDraftPanel from './components/KnowledgeDraftPanel.vue'
import NotesDraftPanel from './components/NotesDraftPanel.vue'
import MemoryModal from './components/MemoryModal.vue'
import WritingEditor from './components/WritingEditor.vue'
import SkillMarketModal from './components/SkillMarketModal.vue'

const store = useTeamStore()
const activeTab = ref<'conversation' | 'knowledge' | 'notes'>('conversation')
const memoryVisible = ref(false)
const skillMarketVisible = ref(false)
const openClawEnabled = ref(localStorage.getItem('openClawEnabled') === 'true')
const chatPrefill = ref<{ id: number; text: string } | null>(null)

const isEditorMode = computed(() => store.editorState.active)

function toggleOpenClaw() {
  openClawEnabled.value = !openClawEnabled.value
  localStorage.setItem('openClawEnabled', String(openClawEnabled.value))
}

const tabItems: Array<{ key: 'conversation' | 'knowledge' | 'notes'; label: string }> = [
  { key: 'conversation', label: '对话' },
  { key: 'knowledge', label: '知识库' },
  { key: 'notes', label: '笔记' },
]

onMounted(async () => {
  await store.fetchTeams()
  await store.fetchAgents()

  // 自动选中第一个团队（恢复历史）
  if (store.teams.length > 0 && !store.currentTeamId) {
    store.selectTeam(store.teams[0].id)
  }

  onMessage((msg) => {
    store.addMessage(msg)
  })
  connect()
})

function handleFillChatInput(text: string) {
  const value = text.trim()
  if (!value) return
  // 笔记回填固定开启新对话，避免污染当前会话上下文
  store.currentTeamId = ''
  chatPrefill.value = {
    id: Date.now(),
    text: value,
  }
  activeTab.value = 'conversation'
}
</script>

<template>
  <div class="app-window">
    <div class="title-bar">

      <div class="title-tabs no-drag">
        <button
          v-for="item in tabItems"
          :key="item.key"
          class="title-tab-btn"
          :class="{ active: activeTab === item.key }"
          @click="activeTab = item.key"
        >
          {{ item.label }}
        </button>
      </div>

      <span class="title-text">Agent Teams</span>

      <div class="title-actions no-drag">
        <button class="action-btn skill-market-btn" @click="skillMarketVisible = true">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
          技能市场
        </button>
        <button
          class="action-btn openclaw-btn"
          :class="{ active: openClawEnabled }"
          @click="toggleOpenClaw"
        >
          <span class="openclaw-dot" :class="{ on: openClawEnabled }"></span>
          OpenClaw
        </button>
        <button class="action-btn memory-btn" @click="memoryVisible = true">记忆</button>
      </div>
    </div>

    <!-- 写作编辑器（全屏覆盖主内容） -->
    <WritingEditor v-if="isEditorMode" class="editor-fullscreen" />

    <!-- 主内容 -->
    <template v-else>
      <div v-if="activeTab === 'conversation'" class="main-content">
        <TeamSidebar class="sidebar" />
        <MemberPanel v-if="store.expertMode" class="info-panel" />
        <ChatArea class="chat-panel" :external-prefill="chatPrefill" />
      </div>

      <KnowledgeDraftPanel v-else-if="activeTab === 'knowledge'" />

      <NotesDraftPanel v-else @fill-chat-input="handleFillChatInput" />
    </template>

    <MemoryModal v-if="memoryVisible" @close="memoryVisible = false" />
    <SkillMarketModal v-if="skillMarketVisible" @close="skillMarketVisible = false" />
  </div>
</template>

<style scoped>
.app-window {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-secondary);
  overflow: hidden;
}

.title-bar {
  height: 38px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  padding: 0 16px;
  -webkit-app-region: drag;
  user-select: none;
  flex-shrink: 0;
}

.traffic-lights {
  display: flex;
  gap: 8px;
  margin-right: 16px;
  flex-shrink: 0;
}

.dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
}

.dot-close { background: #FF5F57; }
.dot-minimize { background: #FFBD2E; }
.dot-maximize { background: #28C840; }

.title-text {
  flex: 1;
  text-align: center;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-muted);
  margin: 0 12px;
}

.no-drag {
  -webkit-app-region: no-drag;
}

.title-tabs {
  display: flex;
  gap: 6px;
}

.title-tab-btn {
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-muted);
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.title-tab-btn:hover {
  background: var(--hover-bg);
  color: var(--text-primary);
}

.title-tab-btn.active {
  background: var(--accent-bg);
  border-color: var(--accent-color);
  color: var(--accent-color);
}

.title-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 6px;
  min-width: 80px;
}

.action-btn {
  border: 1px solid var(--border);
  background: var(--bg-primary);
  color: var(--text-secondary);
  border-radius: 8px;
  font-size: 12px;
  padding: 4px 10px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.action-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.skill-market-btn svg {
  flex-shrink: 0;
}

.openclaw-btn {
  position: relative;
}

.openclaw-btn.active {
  border-color: var(--accent-green);
  color: var(--accent-green);
  background: rgba(52, 199, 89, 0.06);
}

.openclaw-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-muted);
  transition: background 0.2s ease;
  flex-shrink: 0;
}

.openclaw-dot.on {
  background: var(--accent-green);
  box-shadow: 0 0 4px rgba(52, 199, 89, 0.5);
}

.editor-fullscreen {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.main-content {
  flex: 1;
  display: flex;
  min-height: 0;
}

.sidebar {
  width: 240px;
  flex-shrink: 0;
}

.info-panel {
  width: 220px;
  flex-shrink: 0;
}

.chat-panel {
  flex: 1;
  min-width: 0;
}
</style>
