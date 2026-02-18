<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import MarkdownIt from 'markdown-it'
import { useTeamStore } from '../stores/teamStore'

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  typographer: true,
})

interface TodoItem {
  id: string
  text: string
  done: boolean
  dueAt: string
}

interface NoteDraft {
  id: string
  title: string
  content: string
  suggestion: string
  needDivergent: boolean
  lastSuggestFingerprint: string
  suggestionRefs: Array<{ id: number; title: string; url: string; snippet: string }>
  todos: TodoItem[]
  createdAt: string
  updatedAt: string
}

interface SuggestedQuestionItem {
  id: string
  text: string
  refIds: number[]
}

const emit = defineEmits<{
  (e: 'fill-chat-input', text: string): void
}>()
const store = useTeamStore()

const STORAGE_KEY = 'agentteams_notes_drafts_v1'
const notes = ref<NoteDraft[]>([])
const activeNoteId = ref('')
const todoInput = ref('')
const suggestLoading = ref(false)
const suggestError = ref('')
const pipelineLoading = ref(false)
const workflowTip = ref('')
const autoSuggestEnabled = ref(true)
let autoSuggestTimer: ReturnType<typeof setTimeout> | null = null
let suggestElapsedTimer: ReturnType<typeof setInterval> | null = null
const suggestElapsedSec = ref(0)
const contentInputRef = ref<HTMLTextAreaElement | null>(null)
const contentPreviewRef = ref<HTMLDivElement | null>(null)

function formatTimeLabel(date = new Date()) {
  const yyyy = date.getFullYear()
  const mm = String(date.getMonth() + 1).padStart(2, '0')
  const dd = String(date.getDate()).padStart(2, '0')
  const hh = String(date.getHours()).padStart(2, '0')
  const mi = String(date.getMinutes()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}`
}

function createEmptyNote(): NoteDraft {
  const now = new Date()
  const ts = now.toISOString()
  const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  return {
    id,
    title: `笔记 ${formatTimeLabel(now)}`,
    content: '',
    suggestion: '',
    needDivergent: false,
    lastSuggestFingerprint: '',
    suggestionRefs: [],
    todos: [],
    createdAt: ts,
    updatedAt: ts,
  }
}

function saveNotes() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(notes.value))
}

function loadNotes() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) {
      const first = createEmptyNote()
      notes.value = [first]
      activeNoteId.value = first.id
      return
    }
    const parsed = JSON.parse(raw) as NoteDraft[]
    if (!Array.isArray(parsed) || parsed.length === 0) {
      const first = createEmptyNote()
      notes.value = [first]
      activeNoteId.value = first.id
      return
    }
    notes.value = parsed.map((item) => ({
      ...item,
      title: item.title || `笔记 ${formatTimeLabel(new Date(item.createdAt || Date.now()))}`,
      content: item.content || '',
      suggestion: item.suggestion || '',
      needDivergent: Boolean(item.needDivergent),
      lastSuggestFingerprint: item.lastSuggestFingerprint || '',
      suggestionRefs: Array.isArray(item.suggestionRefs) ? item.suggestionRefs : [],
      todos: Array.isArray(item.todos) ? item.todos : [],
      createdAt: item.createdAt || new Date().toISOString(),
      updatedAt: item.updatedAt || new Date().toISOString(),
    }))
    activeNoteId.value = notes.value[0].id
  } catch (error) {
    console.error('Load notes failed:', error)
    const first = createEmptyNote()
    notes.value = [first]
    activeNoteId.value = first.id
  }
}

onMounted(() => {
  loadNotes()
})

watch(
  notes,
  () => {
    saveNotes()
  },
  { deep: true }
)

const activeNote = computed(() => notes.value.find((n) => n.id === activeNoteId.value) || null)
const completedTodos = computed(() => activeNote.value?.todos.filter((t) => t.done).length || 0)
const totalTodos = computed(() => activeNote.value?.todos.length || 0)
const renderedContent = computed(() => md.render(activeNote.value?.content || ''))
const suggestedQuestions = computed(() => parseSuggestedQuestions(activeNote.value?.suggestion || ''))
const suggestionRefMap = computed(() => {
  const map = new Map<number, { id: number; title: string; url: string; snippet: string }>()
  for (const ref of activeNote.value?.suggestionRefs || []) {
    map.set(ref.id, ref)
  }
  return map
})
const currentStep = computed(() => {
  if (!activeNote.value) return 1
  if (!activeNote.value.content.trim()) return 1
  if (!activeNote.value.suggestion.trim()) return 2
  return 3
})

function parseSuggestedQuestions(raw: string): SuggestedQuestionItem[] {
  if (!raw.trim()) return []
  const lines = raw
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .filter((line) => !line.startsWith('###'))

  const normalized = lines
    .map((line) => line.replace(/^\d+[.)、]\s*/, '').replace(/^[-*]\s*/, '').trim())
    .filter((line) => line.length > 0)

  return normalized.slice(0, 3).map((line, idx) => {
    const refIds = Array.from(line.matchAll(/\[(\d+)\]/g)).map((m) => Number(m[1]))
    const cleaned = line
      .replace(/\[(\d+)\]/g, '')
      .replace(/[#*]/g, '')
      .replace(/\s+/g, ' ')
      .trim()
    return {
      id: `${idx}-${cleaned}`,
      text: cleaned,
      refIds,
    }
  })
}

function createNote() {
  const note = createEmptyNote()
  notes.value.unshift(note)
  activeNoteId.value = note.id
}

function removeNote(id: string) {
  const idx = notes.value.findIndex((n) => n.id === id)
  if (idx < 0) return
  notes.value.splice(idx, 1)
  if (notes.value.length === 0) {
    const fallback = createEmptyNote()
    notes.value = [fallback]
    activeNoteId.value = fallback.id
    return
  }
  if (activeNoteId.value === id) {
    activeNoteId.value = notes.value[Math.max(idx - 1, 0)].id
  }
}

function touchNote() {
  if (!activeNote.value) return
  activeNote.value.updatedAt = new Date().toISOString()
}

function addTodo() {
  const text = todoInput.value.trim()
  if (!text || !activeNote.value) return
  activeNote.value.todos.unshift({
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    text,
    done: false,
    dueAt: '',
  })
  todoInput.value = ''
  touchNote()
}

function removeTodo(todoId: string) {
  if (!activeNote.value) return
  activeNote.value.todos = activeNote.value.todos.filter((t) => t.id !== todoId)
  touchNote()
}

function localSuggestion(content: string, needDivergent: boolean) {
  const lines = content
    .split('\n')
    .map((item) => item.trim())
    .filter((item) => item.length > 0)
    .slice(0, 3)
  const focus = lines.join(' / ') || '当前笔记主题'
  const q2 = needDivergent
    ? `2. 围绕“${focus}”，如果要从另一个领域借鉴做法，最值得先验证的一个假设是什么？`
    : `2. 围绕“${focus}”，当前信息里最可能导致执行失败的关键风险是什么，如何提前验证？`
  return [
    '### 推荐问题',
    `1. 如果这份笔记要在 48 小时内落地，第一步最小可执行动作是什么，产出物如何定义？`,
    q2,
    `3. 为了让团队继续推进，这份笔记还缺哪 3 条关键信息（数据、约束或决策）？`,
  ].join('\n')
}

function buildSuggestFingerprint() {
  if (!activeNote.value) return ''
  return [
    activeNote.value.title.trim(),
    activeNote.value.content.trim(),
    activeNote.value.needDivergent ? 'divergent' : 'focused',
  ].join('||')
}

async function suggestForNote(isAuto = false) {
  if (!activeNote.value) return
  if (suggestLoading.value) return false
  if (!isAuto) suggestError.value = ''
  workflowTip.value = ''
  const content = activeNote.value.content.trim()
  if (!content) {
    if (!isAuto) suggestError.value = '请先写一些笔记内容，再生成联想。'
    return false
  }
  suggestLoading.value = true
  suggestElapsedSec.value = 0
  if (suggestElapsedTimer) clearInterval(suggestElapsedTimer)
  suggestElapsedTimer = setInterval(() => {
    suggestElapsedSec.value += 1
  }, 1000)
  try {
    const res = await fetch('/api/notes/suggest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: activeNote.value.title,
        content,
        need_divergent: activeNote.value.needDivergent,
        use_web_search: true,
        team_id: store.currentTeamId || '',
      }),
    })
    if (!res.ok) {
      let detail = `HTTP ${res.status}`
      try {
        const err = await res.json()
        if (err?.detail) detail = String(err.detail)
      } catch {
        // ignore json parse error
      }
      throw new Error(detail)
    }
    const data = await res.json()
    activeNote.value.suggestion = data.suggestion || ''
    activeNote.value.suggestionRefs = Array.isArray(data.references) ? data.references : []
    activeNote.value.lastSuggestFingerprint = buildSuggestFingerprint()
    if (!isAuto) {
      workflowTip.value = data.used_web_search
        ? '已基于联网搜索生成推荐问题。'
        : '已生成推荐问题。'
    }
    touchNote()
    return true
  } catch (error) {
    console.error('Suggest note failed:', error)
    activeNote.value.suggestion = localSuggestion(content, activeNote.value.needDivergent)
    activeNote.value.suggestionRefs = []
    suggestError.value = ''
    workflowTip.value = `大模型联想暂不可用（${error instanceof Error ? error.message : '请求失败'}），已切换为本地推荐问题。`
    touchNote()
    return true
  } finally {
    suggestLoading.value = false
    if (suggestElapsedTimer) {
      clearInterval(suggestElapsedTimer)
      suggestElapsedTimer = null
    }
  }
}

function applySuggestionToNote() {
  if (!activeNote.value || !activeNote.value.suggestion.trim()) return
  activeNote.value.content = activeNote.value.content.trim()
    ? `${activeNote.value.content.trim()}\n\n---\n\n${activeNote.value.suggestion.trim()}`
    : activeNote.value.suggestion.trim()
  touchNote()
}

function buildChatPrefillText() {
  if (!activeNote.value) return ''
  return activeNote.value.content || ''
}

function fillToChatInput() {
  const text = buildChatPrefillText().trim()
  if (!text) return
  emit('fill-chat-input', text)
  workflowTip.value = '已回填到对话输入框，可直接发送继续工作流。'
}

async function runGuidedPipeline() {
  if (!activeNote.value) return
  if (!activeNote.value.content.trim()) {
    workflowTip.value = '请先在中间区域写一点笔记内容。'
    return
  }

  pipelineLoading.value = true
  workflowTip.value = ''
  try {
    if (!activeNote.value.suggestion.trim()) {
      await suggestForNote()
    }
    if (activeNote.value.suggestion.trim()) {
      applySuggestionToNote()
    }
    fillToChatInput()
  } finally {
    pipelineLoading.value = false
  }
}

function handleManualSuggest() {
  void suggestForNote(false)
}

function syncContentPreviewScroll() {
  if (!contentInputRef.value || !contentPreviewRef.value) return
  const input = contentInputRef.value
  const preview = contentPreviewRef.value
  const maxInputScroll = Math.max(input.scrollHeight - input.clientHeight, 1)
  const ratio = input.scrollTop / maxInputScroll
  const maxPreviewScroll = Math.max(preview.scrollHeight - preview.clientHeight, 0)
  preview.scrollTop = ratio * maxPreviewScroll
}

function handleContentInput() {
  touchNote()
  syncContentPreviewScroll()
}

function appendQuestionToNote(question: string) {
  if (!activeNote.value) return
  const line = `- ${question}`
  activeNote.value.content = activeNote.value.content.trim()
    ? `${activeNote.value.content.trim()}\n${line}`
    : line
  touchNote()
  workflowTip.value = '已将推荐问题加入笔记内容。'
}

function askQuestionInChat(item: SuggestedQuestionItem) {
  const text = item.text.trim()
  if (!text) return
  emit('fill-chat-input', text)
  workflowTip.value = '已跳转到对话并回填该问题。'
}

function openReference(refId: number) {
  const ref = suggestionRefMap.value.get(refId)
  if (!ref?.url) return
  window.open(ref.url, '_blank', 'noopener,noreferrer')
}

function buildIcsContent(summary: string, description: string, dueAtLocal: string) {
  const dueDate = new Date(dueAtLocal)
  const safeDate = Number.isNaN(dueDate.getTime()) ? new Date(Date.now() + 3600 * 1000) : dueDate
  const dtStart = new Date(safeDate.getTime() - 30 * 60 * 1000)
  const formatIcs = (date: Date) =>
    `${date.getUTCFullYear()}${String(date.getUTCMonth() + 1).padStart(2, '0')}${String(date.getUTCDate()).padStart(2, '0')}T${String(date.getUTCHours()).padStart(2, '0')}${String(date.getUTCMinutes()).padStart(2, '0')}00Z`
  const uid = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}@agentteams`
  return [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//AgentTeams//NotesTodo//CN',
    'BEGIN:VEVENT',
    `UID:${uid}`,
    `DTSTAMP:${formatIcs(new Date())}`,
    `DTSTART:${formatIcs(dtStart)}`,
    `DTEND:${formatIcs(safeDate)}`,
    `SUMMARY:${summary.replace(/\n/g, ' ')}`,
    `DESCRIPTION:${description.replace(/\n/g, ' ')}`,
    'END:VEVENT',
    'END:VCALENDAR',
  ].join('\r\n')
}

function syncTodoToCalendar(todo: TodoItem) {
  if (!activeNote.value) return
  if (!todo.dueAt) {
    globalThis.alert('请先为该待办设置截止时间，再同步日历。')
    return
  }
  const ics = buildIcsContent(
    `${activeNote.value.title} - ${todo.text}`,
    `来自 AgentTeams 笔记待办：${todo.text}`,
    todo.dueAt
  )
  const blob = new Blob([ics], { type: 'text/calendar;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `todo-${todo.id}.ics`
  link.click()
  URL.revokeObjectURL(url)
}

async function addReminder(todo: TodoItem) {
  if (!todo.dueAt) {
    globalThis.alert('请先设置截止时间，再新增提醒。')
    return
  }

  if (!('Notification' in globalThis)) {
    globalThis.alert('当前环境不支持系统通知，请改用日历同步。')
    return
  }

  let permission = globalThis.Notification.permission
  if (permission === 'default') {
    permission = await globalThis.Notification.requestPermission()
  }
  if (permission !== 'granted') {
    globalThis.alert('未获得通知权限，无法创建提醒。')
    return
  }

  const delay = new Date(todo.dueAt).getTime() - Date.now()
  if (delay <= 0) {
    new globalThis.Notification('待办到期提醒', {
      body: `${activeNote.value?.title || '笔记'}：${todo.text}`,
    })
    return
  }

  setTimeout(() => {
    new globalThis.Notification('待办到期提醒', {
      body: `${activeNote.value?.title || '笔记'}：${todo.text}`,
    })
  }, delay)
  globalThis.alert('提醒已创建，将在截止时间弹出通知。')
}

watch(
  () => [
    activeNoteId.value,
    activeNote.value?.title || '',
    activeNote.value?.content || '',
    activeNote.value?.needDivergent ? '1' : '0',
    autoSuggestEnabled.value ? '1' : '0',
  ],
  () => {
    if (!activeNote.value || !autoSuggestEnabled.value) return
    const content = activeNote.value.content.trim()
    if (!content) return
    const fingerprint = buildSuggestFingerprint()
    if (activeNote.value.lastSuggestFingerprint === fingerprint) return
    if (autoSuggestTimer) clearTimeout(autoSuggestTimer)
    autoSuggestTimer = setTimeout(() => {
      suggestForNote(true)
    }, 1200)
  }
)

onBeforeUnmount(() => {
  if (autoSuggestTimer) {
    clearTimeout(autoSuggestTimer)
    autoSuggestTimer = null
  }
  if (suggestElapsedTimer) {
    clearInterval(suggestElapsedTimer)
    suggestElapsedTimer = null
  }
})

watch(renderedContent, () => {
  queueMicrotask(syncContentPreviewScroll)
})

</script>

<template>
  <div class="draft-panel-wrap">
    <div class="workflow-bar">
      <div class="step-chip" :class="{ active: currentStep === 1 }">1. 写笔记</div>
      <div class="step-chip" :class="{ active: currentStep === 2 }">2. 生成联想</div>
      <div class="step-chip" :class="{ active: currentStep === 3 }">3. 串联对话</div>
      <button class="btn-primary" :disabled="pipelineLoading" @click="runGuidedPipeline">
        {{ pipelineLoading ? '串联中...' : '一键生成并串联到对话' }}
      </button>
    </div>

    <p v-if="workflowTip" class="workflow-tip">{{ workflowTip }}</p>

    <div class="notes-shell" v-if="activeNote">
      <aside class="left-rail">
        <section class="rail-card">
          <div class="sidebar-header">
            <h2>笔记</h2>
            <button class="btn-primary" @click="createNote">+ 新建</button>
          </div>
          <p class="sidebar-desc">先选笔记，再在中间编辑正文。</p>
          <div class="note-list">
            <button
              v-for="note in notes"
              :key="note.id"
              class="note-item"
              :class="{ active: note.id === activeNoteId }"
              @click="activeNoteId = note.id"
            >
              <div class="note-item-title">{{ note.title }}</div>
              <div class="note-item-meta">{{ formatTimeLabel(new Date(note.updatedAt)) }}</div>
            </button>
          </div>
          <button
            class="btn-danger"
            :disabled="!activeNote"
            @click="activeNote ? removeNote(activeNote.id) : null"
          >
            删除当前笔记
          </button>
        </section>

        <section class="rail-card">
          <div class="card-header">
            <h3>待办</h3>
            <span class="meta">{{ completedTodos }}/{{ totalTodos }}</span>
          </div>
          <div class="todo-create">
            <input
              v-model="todoInput"
              class="todo-input"
              placeholder="新增待办，回车添加"
              @keydown.enter.prevent="addTodo"
            />
            <button class="btn-primary" @click="addTodo">添加</button>
          </div>
          <div v-if="activeNote.todos.length === 0" class="todo-empty">暂无待办。</div>
          <div class="todo-list">
            <div v-for="todo in activeNote.todos" :key="todo.id" class="todo-item">
              <label class="todo-check">
                <input type="checkbox" v-model="todo.done" @change="touchNote" />
                <span :class="{ done: todo.done }">{{ todo.text }}</span>
              </label>
              <input
                v-model="todo.dueAt"
                type="datetime-local"
                class="todo-time"
                @change="touchNote"
              />
              <div class="todo-actions">
                <button class="btn-default" @click="syncTodoToCalendar(todo)">日历</button>
                <button class="btn-default" @click="addReminder(todo)">提醒</button>
                <button class="btn-danger mini" @click="removeTodo(todo.id)">删</button>
              </div>
            </div>
          </div>
        </section>
      </aside>

      <main class="center-panel card">
        <div class="card-header">
          <h3>笔记内容</h3>
          <span class="meta">实时 Markdown 渲染</span>
        </div>
        <input
          v-model="activeNote.title"
          class="title-input"
          placeholder="输入笔记标题"
          @input="touchNote"
        />
        <div class="md-live">
          <div ref="contentPreviewRef" class="markdown-preview live-bg" v-html="renderedContent || '<p>暂无内容</p>'"></div>
          <textarea
            ref="contentInputRef"
            v-model="activeNote.content"
            class="content-textarea live-editor"
            placeholder="写下你的想法、摘要、结论..."
            @input="handleContentInput"
            @scroll="syncContentPreviewScroll"
          ></textarea>
        </div>
        <div class="actions-row">
          <button class="btn-primary" @click="fillToChatInput">回填到对话输入</button>
        </div>
      </main>

      <aside class="right-panel card">
        <div class="card-header">
          <h3>推荐内容</h3>
          <div class="right-tools">
            <label class="switch-row">
              <input type="checkbox" v-model="activeNote.needDivergent" @change="touchNote" />
              <span>{{ activeNote.needDivergent ? '发散模式' : '聚焦模式' }}</span>
            </label>
            <label class="switch-row">
              <input type="checkbox" v-model="autoSuggestEnabled" />
              <span>自动联想</span>
            </label>
          </div>
        </div>
        <div class="actions-row">
          <button class="btn-primary" :disabled="suggestLoading" @click="handleManualSuggest">
            {{ suggestLoading ? `生成中 ${suggestElapsedSec}s` : '生成推荐问题' }}
          </button>
          <button class="btn-default" :disabled="!activeNote.suggestion.trim()" @click="applySuggestionToNote">
            回填正文
          </button>
        </div>
        <p v-if="suggestError" class="error-tip">{{ suggestError }}</p>
        <div class="question-list-wrap">
          <button
            v-for="(q, idx) in suggestedQuestions"
            :key="q.id"
            class="question-item"
            @click="askQuestionInChat(q)"
          >
            <span class="q-index">{{ idx + 1 }}</span>
            <span class="q-main">
              <span class="q-text">
                {{ q.text }}
                <span v-if="q.refIds.length > 0" class="q-refs-inline">
                <a
                  v-for="rid in q.refIds"
                  :key="`ref-${q.id}-${rid}`"
                  class="ref-mark-note"
                  :title="suggestionRefMap.get(rid)?.title || `来源 [${rid}]`"
                  @click.stop.prevent="openReference(rid)"
                  href="#"
                >
                  [{{ rid }}]
                </a>
              </span>
              </span>
            </span>
          </button>
          <div v-if="suggestedQuestions.length === 0" class="question-empty">暂无推荐问题，点击上方按钮生成。</div>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.draft-panel-wrap {
  flex: 1;
  min-height: 0;
  padding: 14px;
  background: var(--bg-primary);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.workflow-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-secondary);
  flex-wrap: wrap;
}

.step-chip {
  border: 1px solid var(--border);
  color: var(--text-secondary);
  border-radius: 999px;
  font-size: 12px;
  padding: 4px 10px;
  background: var(--bg-primary);
}

.step-chip.active {
  border-color: var(--accent-color);
  color: var(--accent-color);
  background: var(--accent-bg);
}

.workflow-tip {
  margin: 0;
  padding: 0 4px;
  font-size: 12px;
  color: var(--accent-color);
}

.notes-shell {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 300px minmax(0, 1.8fr) minmax(320px, 1fr);
  gap: 12px;
  align-items: stretch;
}

.left-rail {
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.rail-card {
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-secondary);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
}

.center-panel {
  min-height: 0;
  height: 100%;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sidebar-header h2 {
  margin: 0;
  font-size: 18px;
  color: var(--text-primary);
}

.sidebar-desc {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.4;
}

.note-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.note-item {
  text-align: left;
  border: 1px solid var(--border);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  border-radius: 10px;
  padding: 10px;
  cursor: pointer;
}

.note-item.active {
  border-color: var(--accent-color);
  background: var(--accent-bg);
  color: var(--text-primary);
}

.note-item-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 4px;
}

.note-item-meta {
  font-size: 11px;
  color: var(--text-muted);
}

.card {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px;
  background: var(--bg-primary);
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  overflow: auto;
  min-width: 0;
}

.right-panel {
  min-height: 0;
  height: 100%;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.card-header h3 {
  margin: 0;
  font-size: 14px;
  color: var(--text-primary);
}

.meta {
  font-size: 12px;
  color: var(--text-muted);
}

.title-input,
.todo-input,
.todo-time,
.content-textarea,
.suggestion-textarea {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  outline: none;
}

.title-input,
.todo-input,
.todo-time {
  padding: 8px 10px;
  font-size: 13px;
}

.content-textarea,
.suggestion-textarea {
  min-height: 0;
  height: 100%;
  resize: none;
  padding: 10px;
  line-height: 1.5;
  font-size: 13px;
}

.md-live {
  flex: 1;
  min-height: 0;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-secondary);
  position: relative;
  overflow: hidden;
}

.content-textarea,
.suggestion-textarea {
  border: none;
  border-radius: 0;
  background: transparent;
  min-height: 100%;
  height: 100%;
}

.markdown-preview {
  min-height: 100%;
  height: 100%;
  overflow: auto;
  padding: 12px;
  color: var(--text-primary);
  line-height: 1.65;
  font-size: 13px;
}

.live-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.live-editor {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  padding: 12px;
  background: transparent;
  color: transparent;
  caret-color: var(--text-primary);
  line-height: 1.65;
  font-size: 13px;
}

.markdown-preview :deep(p) {
  margin: 0 0 10px;
}

.markdown-preview :deep(h1),
.markdown-preview :deep(h2),
.markdown-preview :deep(h3) {
  margin: 0 0 8px;
  color: var(--text-primary);
}

.markdown-preview :deep(code) {
  background: rgba(127, 127, 127, 0.15);
  padding: 1px 4px;
  border-radius: 4px;
}

.markdown-preview :deep(pre) {
  padding: 8px;
  border-radius: 8px;
  background: rgba(127, 127, 127, 0.12);
  overflow: auto;
}

.actions-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.switch-row {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

.right-tools {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.question-list-wrap {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 2px;
}

.question-item {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  padding: 10px;
  text-align: left;
  display: flex;
  gap: 10px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.question-item:hover {
  border-color: var(--accent-color);
  background: var(--accent-bg);
}

.q-index {
  width: 20px;
  height: 20px;
  border-radius: 999px;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  flex-shrink: 0;
}

.q-text {
  font-size: 13px;
  line-height: 1.5;
}

.q-main {
  display: block;
  min-width: 0;
}

.q-refs-inline {
  display: inline;
  margin-left: 2px;
}

.ref-mark-note {
  display: inline;
  color: var(--accent);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  padding: 0 1px;
  vertical-align: super;
  line-height: 1;
  transition: color 0.15s, background 0.15s;
  border-radius: 2px;
  text-decoration: none;
}

.ref-mark-note:hover {
  background: rgba(0, 122, 255, 0.12);
  color: #0055cc;
}

.question-empty {
  font-size: 12px;
  color: var(--text-muted);
  border: 1px dashed var(--border);
  border-radius: 10px;
  padding: 12px;
}

.todo-create {
  display: flex;
  gap: 8px;
}

.todo-empty {
  font-size: 12px;
  color: var(--text-muted);
}

.todo-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.todo-item {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.todo-check {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-primary);
  font-size: 13px;
}

.todo-check .done {
  text-decoration: line-through;
  color: var(--text-muted);
}

.todo-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.error-tip {
  margin: 0;
  font-size: 12px;
  color: #ff5f57;
}

.btn-primary,
.btn-default,
.btn-danger {
  border-radius: 8px;
  font-size: 12px;
  padding: 6px 10px;
  cursor: pointer;
}

.btn-primary {
  border: 1px solid var(--accent-color);
  background: var(--accent-bg);
  color: var(--accent-color);
}

.btn-default {
  border: 1px solid var(--border);
  background: var(--bg-secondary);
  color: var(--text-secondary);
}

.btn-danger {
  border: 1px solid #ff5f57;
  background: rgba(255, 95, 87, 0.08);
  color: #ff5f57;
}

.btn-danger.mini {
  padding: 4px 8px;
}

.btn-primary:disabled,
.btn-default:disabled,
.btn-danger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

@media (max-width: 1180px) {
  .notes-shell {
    grid-template-columns: 1fr;
  }
}
</style>
