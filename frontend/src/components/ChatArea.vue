<script setup lang="ts">
import { ref, computed, nextTick, watch, onMounted } from 'vue'
import { useTeamStore } from '../stores/teamStore'
import MessageCard from './MessageCard.vue'
import ScenePanel from './ScenePanel.vue'

const props = defineProps<{
  externalPrefill?: { id: number; text: string } | null
}>()

const store = useTeamStore()
const inputText = ref('')
const filePaths = ref('')
const showFileInput = ref(false)
const enableReview = ref(false)
const chatContainer = ref<HTMLElement>()
const submitting = ref(false)
const lastAppliedPrefillId = ref<number | null>(null)

const messages = computed(() => store.currentMessages)

watch(
  () => props.externalPrefill,
  (payload) => {
    if (!payload?.text) return
    if (payload.id === lastAppliedPrefillId.value) return
    lastAppliedPrefillId.value = payload.id

    inputText.value = payload.text
    filePaths.value = ''
    showFileInput.value = false
  },
  { immediate: true, deep: true }
)

// ====== 模型切换 ======
interface ModelInfo {
  id: string
  name: string
  desc: string
}
const models = ref<ModelInfo[]>([])
const currentModel = ref('')
const showModelPicker = ref(false)

async function fetchModels() {
  try {
    const res = await fetch('/api/models')
    const data = await res.json()
    models.value = data.models
    currentModel.value = data.current
  } catch (e) {
    console.error('Failed to fetch models:', e)
  }
}

async function switchModel(modelId: string) {
  try {
    const res = await fetch('/api/models/switch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_id: modelId }),
    })
    if (res.ok) {
      currentModel.value = modelId
    }
  } catch (e) {
    console.error('Failed to switch model:', e)
  }
  showModelPicker.value = false
}

const currentModelName = computed(() => {
  const m = models.value.find(m => m.id === currentModel.value)
  return m?.name || currentModel.value || '选择模型'
})

onMounted(() => {
  fetchModels()
})

const exampleTasks = [
  { text: '分析人工智能在教育领域的应用前景和潜在风险', hasFile: false },
  { text: '审查这个项目的代码质量和架构问题', hasFile: true, path: '~/Projects/my-app/src' },
  { text: '撰写一份关于多Agent协作平台的产品发布通稿', hasFile: false },
]

// ====== 智能滚动：用户滚动查看时不强制回底部 ======
const userNearBottom = ref(true)

function onChatScroll() {
  if (!chatContainer.value) return
  const el = chatContainer.value
  const threshold = 150 // 距底部 150px 以内视为"在底部"
  userNearBottom.value = (el.scrollHeight - el.scrollTop - el.clientHeight) < threshold
}

function scrollToBottom(force = false) {
  if (!chatContainer.value) return
  if (force || userNearBottom.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}

// 新消息到达时：仅在靠近底部时自动滚动
watch(
  () => messages.value.length,
  async () => {
    await nextTick()
    scrollToBottom()
  }
)

// 流式内容更新时：仅在靠近底部时自动滚动（节流 80ms）
let scrollThrottleTimer: ReturnType<typeof setTimeout> | null = null
watch(
  () => store.streamTick,
  () => {
    if (!scrollThrottleTimer) {
      scrollThrottleTimer = setTimeout(async () => {
        scrollThrottleTimer = null
        await nextTick()
        scrollToBottom()
      }, 80)
    }
  }
)

async function handleSubmit() {
  const text = inputText.value.trim()
  if (!text || submitting.value) return

  // 同步操作：立即清空输入框和锁定状态，避免竞态
  submitting.value = true
  const currentFiles = filePaths.value
  inputText.value = ''
  filePaths.value = ''
  userNearBottom.value = true

  try {
    if (!store.currentTeamId) {
      const now = new Date()
      const timeLabel = `${now.getMonth() + 1}/${now.getDate()} ${now.getHours()}:${String(now.getMinutes()).padStart(2, '0')}`
      await store.createTeam(`新对话 ${timeLabel}`)
    }

    await nextTick()
    scrollToBottom(true)

    const paths = currentFiles
      .split(/[\n,]/)
      .map(p => p.trim())
      .filter(p => p.length > 0)

    const res = await fetch('/api/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: text.slice(0, 80),
        description: text,
        team_id: store.currentTeamId,
        file_paths: paths,
        enable_review: enableReview.value,
      }),
    })

    if (!res.ok) {
      console.error('Task submission failed:', res.statusText)
    }
  } catch (e) {
    console.error('Failed to submit task:', e)
  } finally {
    submitting.value = false
  }
}

function useExample(example: typeof exampleTasks[0]) {
  inputText.value = example.text
  if (example.hasFile && example.path) {
    showFileInput.value = true
    filePaths.value = example.path
  }
}

async function handleSceneSubmit(payload: {
  description: string
  title: string
  sceneType: string
  sceneCategory: string
  sceneFormData: Record<string, string>
}) {
  if (submitting.value) return
  submitting.value = true

  try {
    let teamId = store.currentTeamId
    if (!teamId) {
      const team = await store.createTeam(payload.title, '')
      teamId = team.id
    }

    await fetch('/api/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: payload.title,
        description: payload.description,
        team_id: teamId,
        enable_review: enableReview.value,
        scene_type: payload.sceneType,
        scene_category: payload.sceneCategory,
        scene_form_data: payload.sceneFormData,
      }),
    })
  } catch (e) {
    console.error('Failed to submit scene task:', e)
  } finally {
    submitting.value = false
  }
}

const stopping = ref(false)

async function handleStop() {
  if (!store.currentTeamId || stopping.value) return
  stopping.value = true
  try {
    await fetch(`/api/teams/${store.currentTeamId}/stop`, { method: 'POST' })
  } catch (e) {
    console.error('Failed to stop task:', e)
  } finally {
    stopping.value = false
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSubmit()
  }
}

const isWorking = computed(() => {
  if (messages.value.length === 0) return false
  if (submitting.value) return true
  // 还有流式中的消息 → 工作中
  const hasStreaming = messages.value.some(m => m.metadata?.streaming === true)
  if (hasStreaming) return true
  // 最后一条是非完成状态的 status_update → 工作中
  const last = messages.value[messages.value.length - 1]
  if (last.type === 'status_update' && last.metadata?.status !== 'completed') return true
  return false
})
</script>

<template>
  <div class="chat-root">
    <!-- Header -->
    <div class="chat-header">
      <div>
        <h2 class="chat-title">{{ store.currentTeam?.name || 'Agent Teams' }}</h2>
        <p v-if="store.currentTeam" class="chat-subtitle">{{ messages.length }} 条消息</p>
      </div>
    </div>

    <!-- 消息区域 -->
    <div ref="chatContainer" class="chat-messages" @scroll="onChatScroll">
      <div class="messages-inner">
        <MessageCard
          v-for="msg in messages"
          :key="msg.id"
          :message="msg"
        />
      </div>

      <!-- 空状态：场景面板 + 示例 -->
      <div v-if="messages.length === 0" class="empty-welcome">
        <div class="welcome-content">
          <ScenePanel @submit="handleSceneSubmit" />

          <div class="example-section">
            <p class="example-label">或试试这些示例</p>
            <div class="example-list">
              <button
                v-for="(example, idx) in exampleTasks"
                :key="idx"
                @click="useExample(example)"
                class="example-btn"
              >
                <span>{{ example.text }}</span>
                <span v-if="example.hasFile" class="file-badge">📎 含文件</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 工作中指示器 -->
      <div v-if="isWorking" class="working-indicator">
        <div class="dots">
          <span class="dot" style="animation-delay: 0ms"></span>
          <span class="dot" style="animation-delay: 150ms"></span>
          <span class="dot" style="animation-delay: 300ms"></span>
        </div>
        <span class="working-text">专家团队协作中...</span>
      </div>
    </div>

    <!-- 输入区域 -->
    <div class="input-area">
      <!-- 文件路径输入 -->
      <div v-if="showFileInput" class="file-input-section">
        <div class="file-input-header">
          <span class="file-label">📎 附加文件路径</span>
          <button @click="showFileInput = false; filePaths = ''" class="file-close">关闭</button>
        </div>
        <textarea
          v-model="filePaths"
          placeholder="输入本地文件或目录路径，多个路径用换行分隔"
          rows="2"
          class="file-textarea"
        ></textarea>
      </div>

      <!-- 工具栏 -->
      <div class="input-toolbar">
        <!-- 模型选择器 -->
        <div class="model-picker-wrapper">
          <button
            @click="showModelPicker = !showModelPicker"
            class="btn-model"
            :class="{ active: showModelPicker }"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" class="model-icon">
              <path d="M7 1L1 4l6 3 6-3-6-3zM1 10l6 3 6-3M1 7l6 3 6-3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <span class="model-name">{{ currentModelName }}</span>
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none" class="chevron" :class="{ open: showModelPicker }">
              <path d="M2.5 4L5 6.5 7.5 4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>

          <!-- 下拉列表 -->
          <Transition name="dropdown">
            <div v-if="showModelPicker" class="model-dropdown">
              <button
                v-for="m in models"
                :key="m.id"
                @click="switchModel(m.id)"
                class="model-option"
                :class="{ selected: m.id === currentModel }"
              >
                <span class="model-option-name">{{ m.name }}</span>
                <span class="model-option-desc">{{ m.desc }}</span>
                <svg v-if="m.id === currentModel" width="14" height="14" viewBox="0 0 14 14" fill="none" class="check-icon">
                  <path d="M3 7.5l3 3 5-6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </button>
            </div>
          </Transition>

          <!-- 点击外部关闭 -->
          <div v-if="showModelPicker" class="model-backdrop" @click="showModelPicker = false"></div>
        </div>

        <button
          @click="showFileInput = !showFileInput"
          class="btn-attach"
          :class="{ active: showFileInput || filePaths.trim() }"
          title="附加文件"
        >
          <svg width="16" height="16" viewBox="0 0 18 18" fill="none">
            <path d="M15.5 8.5L9.17 14.83a3.5 3.5 0 01-4.95-4.95L10.58 3.5a2.33 2.33 0 013.3 3.3L7.52 13.17a1.17 1.17 0 01-1.65-1.65L11.7 5.7" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>

        <!-- 审查开关 -->
        <button
          @click="enableReview = !enableReview"
          class="btn-review"
          :class="{ active: enableReview }"
          :title="enableReview ? '审查已开启：回答将经过核查专家验证' : '点击开启审查：核查专家将验证回答准确性'"
        >
          <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
            <path d="M8 1a7 7 0 100 14A7 7 0 008 1z" stroke="currentColor" stroke-width="1.2"/>
            <path d="M5.5 8.5l2 2 3.5-4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <span class="review-label">审查</span>
        </button>
      </div>

      <!-- 主输入框 -->
      <div class="input-box">
        <textarea
          v-model="inputText"
          @keydown="handleKeydown"
          :placeholder="isWorking ? '等待任务完成...' : '描述你的任务...'"
          rows="1"
          class="main-textarea"
          :disabled="isWorking"
        ></textarea>

        <!-- 终止按钮（工作中时显示） -->
        <button
          v-if="isWorking"
          @click="handleStop"
          :disabled="stopping"
          class="btn-stop"
          :class="{ stopping: stopping }"
          title="终止对话"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <rect x="3" y="3" width="8" height="8" rx="1.5" fill="currentColor"/>
          </svg>
        </button>

        <!-- 发送按钮（空闲时显示） -->
        <button
          v-else
          @click="handleSubmit"
          :disabled="!inputText.trim() || submitting"
          class="btn-send"
          :class="{ ready: inputText.trim() && !submitting }"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M14 2L7.5 8.5M14 2l-4.5 12-2-5.5L2 6.5 14 2z" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-root {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-card);
}

.chat-header {
  padding: 16px 28px 14px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.chat-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

.chat-subtitle {
  font-size: 12px;
  color: var(--text-light);
  margin-top: 2px;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  position: relative;
  min-height: 0;
}

.messages-inner {
  padding: 8px 0;
}

/* 空状态 */
.empty-welcome {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  min-height: 100%;
  padding: 20px 0 24px;
  box-sizing: border-box;
}

.welcome-content {
  text-align: center;
  width: min(100%, 980px);
  padding: 0 24px;
  box-sizing: border-box;
}

.welcome-icon {
  margin-bottom: 16px;
  display: flex;
  justify-content: center;
}

.welcome-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.03em;
  margin-bottom: 8px;
}

.welcome-desc {
  font-size: 15px;
  line-height: 1.6;
  color: var(--text-muted);
  margin-bottom: 32px;
}

.example-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-light);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 12px;
}

.example-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.example-btn {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  text-align: left;
  padding: 12px 16px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-secondary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
  line-height: 1.5;
}

.example-btn:hover {
  border-color: var(--accent);
  background: var(--bg-active);
  color: var(--text-primary);
}

.file-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 20px;
  background: var(--bg-secondary);
  color: var(--accent);
  flex-shrink: 0;
  margin-left: 12px;
}

/* 工作指示器 */
.working-indicator {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 28px 16px;
}

.dots {
  display: flex;
  gap: 4px;
}

.dots .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  animation: bounce 1.2s infinite;
}

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

.working-text {
  font-size: 13px;
  color: var(--text-muted);
}

/* 输入区域 */
.input-area {
  padding: 12px 24px 20px;
  flex-shrink: 0;
}

.file-input-section {
  margin-bottom: 10px;
  padding: 12px 16px;
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
}

.file-input-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.file-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--accent);
}

.file-close {
  font-size: 12px;
  color: var(--text-muted);
  background: none;
  border: none;
  cursor: pointer;
}

.file-close:hover { color: var(--text-secondary); }

.file-textarea {
  width: 100%;
  background: transparent;
  border: none;
  outline: none;
  resize: none;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-primary);
}

.input-box {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 10px 12px 10px 14px;
  border-radius: var(--radius-lg);
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.input-box:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.08);
}

/* 工具栏 */
.input-toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 8px;
}

/* 模型选择器 */
.model-picker-wrapper {
  position: relative;
}

.btn-model {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.btn-model:hover {
  border-color: var(--accent);
  color: var(--text-primary);
}

.btn-model.active {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--bg-active);
}

.model-icon {
  opacity: 0.65;
  flex-shrink: 0;
}

.model-name {
  font-weight: 500;
}

.chevron {
  transition: transform 0.2s;
  opacity: 0.5;
}

.chevron.open {
  transform: rotate(180deg);
}

.model-backdrop {
  position: fixed;
  inset: 0;
  z-index: 99;
}

.model-dropdown {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  min-width: 280px;
  max-height: 360px;
  overflow-y: auto;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12), 0 2px 8px rgba(0, 0, 0, 0.06);
  z-index: 100;
  padding: 6px;
}

.model-option {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.12s;
  text-align: left;
}

.model-option:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.model-option.selected {
  background: var(--bg-active);
  color: var(--accent);
}

.model-option-name {
  font-weight: 500;
  flex-shrink: 0;
}

.model-option-desc {
  font-size: 11px;
  color: var(--text-light);
  flex: 1;
}

.check-icon {
  color: var(--accent);
  flex-shrink: 0;
}

/* 下拉动画 */
.dropdown-enter-active,
.dropdown-leave-active {
  transition: all 0.15s ease;
}

.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(4px);
}

.btn-attach {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  border: none;
  background: transparent;
  color: var(--text-light);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
  flex-shrink: 0;
}

.btn-attach:hover { color: var(--text-secondary); background: var(--bg-hover); }
.btn-attach.active { color: var(--accent); }

/* 审查开关 */
.btn-review {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-light);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.btn-review:hover {
  border-color: var(--text-muted);
  color: var(--text-secondary);
  background: var(--bg-hover);
}

.btn-review.active {
  border-color: #34C759;
  color: #34C759;
  background: rgba(52, 199, 89, 0.08);
}

.review-label {
  font-weight: 500;
}

.main-textarea {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  resize: none;
  font-size: 15px;
  line-height: 1.5;
  color: var(--text-primary);
  max-height: 120px;
  padding: 4px 0;
}

.main-textarea::placeholder {
  color: var(--text-light);
}

.btn-send {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  background: var(--bg-tertiary);
  color: var(--text-light);
  cursor: not-allowed;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  flex-shrink: 0;
}

.btn-send.ready {
  background: var(--accent);
  color: white;
  cursor: pointer;
}

.btn-send.ready:hover {
  opacity: 0.85;
}

/* 终止按钮 */
.btn-stop {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 2px solid var(--text-secondary);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  flex-shrink: 0;
}

.btn-stop:hover {
  border-color: #FF3B30;
  color: #FF3B30;
  background: rgba(255, 59, 48, 0.06);
}

.btn-stop.stopping {
  opacity: 0.5;
  cursor: wait;
  animation: pulse-stop 1s ease-in-out infinite;
}

@keyframes pulse-stop {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 0.3; }
}

.main-textarea:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
