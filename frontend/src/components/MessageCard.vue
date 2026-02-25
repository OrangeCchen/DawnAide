<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import MarkdownIt from 'markdown-it'
import type { Message } from '../types'
import { useTeamStore } from '../stores/teamStore'

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  typographer: true,
})

const props = defineProps<{
  message: Message
}>()

const store = useTeamStore()

const isUser = computed(() => props.message.sender === 'user')
const isStatus = computed(() => props.message.type === 'status_update')
const isTaskResult = computed(() => props.message.type === 'task_result')
const isThinking = computed(() => props.message.metadata?.is_thinking === true)

const isStreaming = computed(() => props.message.metadata?.streaming === true)

const expertName = computed(() => props.message.metadata?.expert_name || '')
const isExpertResult = computed(() => isTaskResult.value && !!expertName.value)
const isDiscussion = computed(() => props.message.metadata?.is_discussion === true)
const expertRound = computed(() => props.message.metadata?.round || 1)
const isError = computed(() => props.message.metadata?.error === true || props.message.metadata?.status_label === 'FAILED')
const isStopped = computed(() => props.message.metadata?.stopped === true)
const hasSearch = computed(() => props.message.metadata?.has_search === true)
const hasUrlRead = computed(() => props.message.metadata?.has_url_read === true)
const hasImessage = computed(() => props.message.metadata?.has_imessage === true)
const isFinalAnswer = computed(() =>
  isTaskResult.value && !expertName.value && props.message.sender === 'team-lead' && !isError.value
)

// ====== 信息补充卡片 ======
const infoRequest = computed(() => props.message.metadata?.info_request)
const isInfoRequest = computed(() => !!infoRequest.value?.fields?.length)
const infoFields = computed(() => infoRequest.value?.fields || [])
const originalTask = computed(() => props.message.metadata?.original_task || '')

// 卡片表单状态 — 使用 ref 对象 + 手动更新验证状态，确保响应式可靠
const formData = ref<Record<string, string | string[]>>({})
const formValid = ref(false)
const infoSubmitted = ref(false)
const infoSubmitting = ref(false)

// 初始化字段默认值
watch(infoFields, (fields) => {
  const data = { ...formData.value }
  for (const f of fields) {
    if (!(f.id in data)) {
      data[f.id] = f.type === 'multiselect' ? [] : ''
    }
  }
  formData.value = data
  recheckValidity()
}, { immediate: true })

function recheckValidity() {
  const data = formData.value
  for (const field of infoFields.value) {
    if (!field.required) continue
    const val = data[field.id]
    if (!val || (Array.isArray(val) && val.length === 0) || (typeof val === 'string' && !val.trim())) {
      formValid.value = false
      return
    }
  }
  formValid.value = true
}

function onFieldInput(fieldId: string, value: string) {
  formData.value = { ...formData.value, [fieldId]: value }
  recheckValidity()
}

function onSelectField(fieldId: string, option: string) {
  formData.value = { ...formData.value, [fieldId]: option }
  recheckValidity()
}

function toggleMultiSelect(fieldId: string, option: string) {
  const current = formData.value[fieldId]
  const arr = Array.isArray(current) ? [...current] : []
  const idx = arr.indexOf(option)
  if (idx >= 0) arr.splice(idx, 1)
  else arr.push(option)
  formData.value = { ...formData.value, [fieldId]: arr }
  recheckValidity()
}

function onInfoTextInput(fieldId: string, event: Event) {
  const target = event.target as HTMLInputElement | null
  onFieldInput(fieldId, target?.value ?? '')
}

function isMultiSelected(fieldId: string, option: string) {
  const val = formData.value[fieldId]
  return Array.isArray(val) && val.includes(option)
}

function hasFieldValue(fieldId: string) {
  const val = formData.value[fieldId]
  if (Array.isArray(val)) return val.length > 0
  if (typeof val === 'string') return val.trim().length > 0
  return false
}

function getFieldDisplayValue(fieldId: string) {
  const val = formData.value[fieldId]
  if (Array.isArray(val)) return val.join('、')
  return typeof val === 'string' ? val : ''
}

async function submitInfoCard() {
  if (!formValid.value || infoSubmitting.value || infoSubmitted.value) return
  infoSubmitting.value = true

  try {
    // 拼接补充信息
    const parts: string[] = []
    const data = formData.value
    for (const field of infoFields.value) {
      const val = data[field.id]
      if (!val || (Array.isArray(val) && val.length === 0) || (typeof val === 'string' && !val.trim())) continue
      const display = Array.isArray(val) ? val.join('、') : val
      parts.push(`${field.label}：${display}`)
    }
    const supplement = parts.join('\n')
    const fullDescription = `${originalTask.value}\n\n--- 用户补充信息 ---\n${supplement}`

    const res = await fetch('/api/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: originalTask.value.slice(0, 80),
        description: fullDescription,
        team_id: store.currentTeamId,
      }),
    })

    if (res.ok) {
      infoSubmitted.value = true
    }
  } catch (e) {
    console.error('Failed to submit info card:', e)
  } finally {
    infoSubmitting.value = false
  }
}

// 统计数据
const elapsed = computed(() => props.message.metadata?.elapsed)
const estTokens = computed(() => props.message.metadata?.est_tokens)
const charCount = computed(() => props.message.content?.length || 0)

// 完成状态消息
const isCompletionStatus = computed(() =>
  isStatus.value && props.message.metadata?.status === 'completed'
)

// ====== 复制 / 导出 ======
const copySuccess = ref(false)
const exporting = ref(false)
const userCopySuccess = ref(false)
const userRetrying = ref(false)
const userRetrySuccess = ref(false)

async function copyAsText() {
  try {
    await navigator.clipboard.writeText(props.message.content || '')
    copySuccess.value = true
    setTimeout(() => { copySuccess.value = false }, 2000)
  } catch (e) {
    console.error('Copy failed:', e)
  }
}

async function exportWord() {
  if (exporting.value) return
  exporting.value = true
  try {
    const res = await fetch('/api/export/word', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        content: props.message.content || '',
        title: '文档',
        doc_type: 'general',
      }),
    })
    if (res.ok) {
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      const disposition = res.headers.get('content-disposition')
      const filenameMatch = disposition?.match(/filename=(.+)/)
      a.href = url
      a.download = filenameMatch ? filenameMatch[1] : '文档.docx'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    }
  } catch (e) {
    console.error('Export failed:', e)
  } finally {
    exporting.value = false
  }
}

async function copyUserMessage() {
  try {
    await navigator.clipboard.writeText(props.message.content || '')
    userCopySuccess.value = true
    setTimeout(() => { userCopySuccess.value = false }, 2000)
  } catch (e) {
    console.error('Copy user message failed:', e)
  }
}

async function retryUserMessage() {
  const content = (props.message.content || '').trim()
  if (!content || !store.currentTeamId || userRetrying.value) return

  userRetrying.value = true
  try {
    const res = await fetch('/api/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: content.slice(0, 80),
        description: content,
        team_id: store.currentTeamId,
      }),
    })

    if (res.ok) {
      userRetrySuccess.value = true
      setTimeout(() => { userRetrySuccess.value = false }, 2000)
    }
  } catch (e) {
    console.error('Retry user message failed:', e)
  } finally {
    userRetrying.value = false
  }
}

const expanded = ref(false)

// 引用角标 tooltip
const tooltipVisible = ref(false)
const tooltipX = ref(0)
const tooltipY = ref(0)
const tooltipTitle = ref('')
const tooltipSnippet = ref('')
const tooltipUrl = ref('')
const cardEl = ref<HTMLElement | null>(null)

function handleMouseOver(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (target.classList.contains('ref-mark')) {
    tooltipTitle.value = target.dataset.refTitle || ''
    tooltipSnippet.value = target.dataset.refSnippet || ''
    tooltipUrl.value = target.dataset.refUrl || ''

    const rect = target.getBoundingClientRect()
    tooltipX.value = rect.left + rect.width / 2
    tooltipY.value = rect.top - 8
    tooltipVisible.value = true
  }
}

function handleMouseOut(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (target.classList.contains('ref-mark')) {
    tooltipVisible.value = false
  }
}

function handleRefClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (target.classList.contains('ref-mark') && tooltipUrl.value) {
    window.open(tooltipUrl.value, '_blank')
  }
}

const timeAgo = computed(() => {
  const ts = new Date(props.message.timestamp)
  const diff = Date.now() - ts.getTime()
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}小时前`
  return `${Math.floor(hours / 24)}天前`
})

const references = computed<Array<{id: number; title: string; url: string; snippet: string}>>(() => {
  return props.message.metadata?.references || []
})

const renderedContent = computed(() => {
  const raw = props.message.formatted_content || props.message.content || ''
  let html = md.render(raw)

  // 将 [N] 角标转为可交互的 tooltip 元素
  if (references.value.length > 0) {
    html = html.replace(/\[(\d+)\]/g, (_match, num) => {
      const refId = parseInt(num)
      const ref = references.value.find(r => r.id === refId)
      if (ref) {
        const escapedTitle = ref.title.replace(/"/g, '&quot;').replace(/'/g, '&#39;')
        const escapedSnippet = ref.snippet.replace(/"/g, '&quot;').replace(/'/g, '&#39;')
        const escapedUrl = ref.url.replace(/"/g, '&quot;')
        return `<sup class="ref-mark" data-ref-id="${refId}" data-ref-title="${escapedTitle}" data-ref-snippet="${escapedSnippet}" data-ref-url="${escapedUrl}">[${num}]</sup>`
      }
      return `[${num}]`
    })
  }

  // 将"示例迁移："标题 + 紧跟的列表包裹为可折叠 details 元素
  html = html.replace(
    /<p>示例迁移：<\/p>\n?(<ul>[\s\S]*?<\/ul>)/,
    '<details class="inline-collapse"><summary>示例迁移（点击展开）</summary>\n$1</details>'
  )

  return html
})

const previewContent = computed(() => {
  const raw = props.message.content || ''
  const plain = raw.replace(/[*#`_~\[\]()>|-]/g, '').replace(/\n/g, ' ')
  if (plain.length <= 100) return plain
  return plain.slice(0, 100) + '...'
})

function formatTokens(n: number): string {
  if (!n) return ''
  if (n < 1000) return `${n}`
  return `${(n / 1000).toFixed(1)}k`
}
</script>

<template>
  <!-- 状态消息 -->
  <div v-if="isStatus" class="msg-status" :class="{
    'msg-status-done': isCompletionStatus && !isError && !isStopped,
    'msg-status-error': isCompletionStatus && isError,
    'msg-status-stopped': isCompletionStatus && isStopped,
  }">
    <span v-if="isCompletionStatus && isError" class="status-error-dot">✗</span>
    <span v-else-if="isCompletionStatus && isStopped" class="status-stopped-dot">⏹</span>
    <span v-else-if="isCompletionStatus" class="status-done-dot">✓</span>
    <span v-else class="status-dot"></span>
    <span class="status-text" v-html="md.renderInline(message.content || '')"></span>
    <span
      v-for="skill in (message.metadata?.skills_used || [])"
      :key="skill"
      class="skill-tag"
    >{{ skill }}</span>
  </div>

  <!-- 用户消息 -->
  <div v-else-if="isUser" class="msg-user">
    <div class="msg-header">
      <div class="avatar avatar-user">U</div>
      <span class="sender-name">你</span>
      <span class="msg-time user-msg-time">{{ timeAgo }}</span>
      <div class="msg-actions user-msg-actions">
        <button class="action-btn" @click="copyUserMessage" :title="userCopySuccess ? '已复制' : '复制问题'">
          {{ userCopySuccess ? '✓ 已复制' : '📋 复制' }}
        </button>
        <button class="action-btn" @click="retryUserMessage" :disabled="userRetrying">
          {{ userRetrying ? '重试中...' : (userRetrySuccess ? '✓ 已重试' : '🔁 重试') }}
        </button>
      </div>
    </div>
    <div class="msg-content user-text">{{ message.content }}</div>
  </div>

  <!-- 思考过程 -->
  <div v-else-if="isThinking" class="msg-thinking">
    <div class="msg-header">
      <div class="avatar avatar-lead">TL</div>
      <span class="sender-name">任务分析</span>
      <span class="thinking-badge">已完成</span>
      <span v-if="elapsed" class="meta-info">{{ elapsed }}s</span>
      <span class="msg-time">{{ timeAgo }}</span>
    </div>
    <div class="msg-content thinking-content markdown-body" v-html="renderedContent"></div>
  </div>

  <!-- 专家结果（可折叠）：Round 1 独立分析 / Round 2 协作讨论 -->
  <div v-else-if="isExpertResult" class="msg-expert" :class="{ 'msg-expert-discuss': isDiscussion }">
    <button @click="expanded = !expanded" class="expert-toggle">
      <span class="toggle-arrow" :class="{ open: expanded }">
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
          <path d="M3.5 2L7 5L3.5 8" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </span>
      <span class="expert-avatar" :class="{ 'expert-avatar-discuss': isDiscussion }">
        {{ isDiscussion ? '💬' : expertName.charAt(0) }}
      </span>
      <span class="expert-name">{{ expertName }}</span>
      <span v-if="hasSearch" class="search-tag" title="已联网搜索">🔍</span>
      <span v-if="hasUrlRead" class="url-read-tag" title="已读取网页">📄</span>
      <span v-if="hasImessage" class="imessage-tag" title="已发送iMessage">💬</span>
      <span v-if="isDiscussion" class="round-label">协作讨论</span>
      <span v-else class="round-label round-label-r1">独立分析</span>

      <!-- 流式中：显示进度 -->
      <template v-if="isStreaming">
        <span class="expert-badge streaming-badge">输出中</span>
        <span class="expert-char-count">{{ charCount }} 字</span>
      </template>
      <!-- 完成：显示统计 -->
      <template v-else>
        <span class="expert-badge">完成</span>
        <span v-if="elapsed" class="meta-info">{{ elapsed }}s</span>
        <span v-if="estTokens" class="meta-info">~{{ formatTokens(estTokens) }} tok</span>
        <span v-if="!expanded" class="expert-preview">{{ previewContent }}</span>
      </template>
    </button>
    <!-- 仅手动展开时显示内容，流式中不展开 -->
    <div v-if="expanded" class="expert-content markdown-body" v-html="renderedContent"></div>
    <div v-if="expanded && !isStreaming" class="msg-actions expert-content-actions">
      <button class="action-btn" @click="copyAsText" :title="copySuccess ? '已复制' : '复制文本'">
        {{ copySuccess ? '✓ 已复制' : '📋 复制' }}
      </button>
      <button class="action-btn" @click="exportWord" :disabled="exporting">
        {{ exporting ? '导出中...' : '📄 Word' }}
      </button>
    </div>
  </div>

  <!-- 信息补充卡片 -->
  <div v-else-if="isInfoRequest" class="msg-info-card">
    <div class="msg-header">
      <div class="avatar avatar-lead">TL</div>
      <span class="sender-name">需要补充信息</span>
      <span v-if="infoSubmitted" class="info-badge info-badge-done">已提交</span>
      <span v-else class="info-badge">待填写</span>
      <span class="msg-time">{{ timeAgo }}</span>
    </div>
    <div class="msg-content">
      <p class="info-message">{{ infoRequest.message || '请补充以下信息：' }}</p>

      <div v-if="!infoSubmitted" class="info-fields">
        <div v-for="field in infoFields" :key="field.id" class="info-field">
          <label class="field-label">
            {{ field.label }}
            <span v-if="field.required" class="field-required">*</span>
          </label>

          <!-- 单选 -->
          <div v-if="field.type === 'select'" class="field-options">
            <button
              v-for="opt in field.options"
              :key="opt"
              @click="onSelectField(field.id, opt)"
              class="option-btn"
              :class="{ selected: formData[field.id] === opt }"
            >{{ opt }}</button>
          </div>

          <!-- 多选 -->
          <div v-else-if="field.type === 'multiselect'" class="field-options">
            <button
              v-for="opt in field.options"
              :key="opt"
              @click="toggleMultiSelect(field.id, opt)"
              class="option-btn"
              :class="{ selected: isMultiSelected(field.id, opt) }"
            >{{ opt }}</button>
          </div>

          <!-- 文本输入 -->
          <div v-else class="field-text">
            <input
              type="text"
              :placeholder="field.placeholder || '请输入...'"
              :value="formData[field.id] || ''"
              @input="onInfoTextInput(field.id, $event)"
              class="text-input"
            />
          </div>
        </div>
      </div>

      <!-- 已提交的回显 -->
      <div v-else class="info-submitted-summary">
        <div v-for="field in infoFields" :key="field.id" class="submitted-item">
          <template v-if="hasFieldValue(field.id)">
            <span class="submitted-label">{{ field.label }}：</span>
            <span class="submitted-value">{{ getFieldDisplayValue(field.id) }}</span>
          </template>
        </div>
      </div>

      <button
        v-if="!infoSubmitted"
        @click="submitInfoCard"
        :disabled="!formValid || infoSubmitting"
        class="info-submit-btn"
        :class="{ ready: formValid && !infoSubmitting }"
      >
        {{ infoSubmitting ? '提交中...' : '确认并继续' }}
      </button>
    </div>
  </div>

  <!-- 错误消息 -->
  <div v-else-if="isError && isTaskResult" class="msg-error">
    <div class="msg-header">
      <div class="avatar avatar-error">!</div>
      <span class="sender-name">执行失败</span>
      <span class="error-badge">错误</span>
      <span class="msg-time">{{ timeAgo }}</span>
    </div>
    <div class="msg-content error-text">{{ message.content }}</div>
  </div>

  <!-- 最终答案 -->
  <div v-else-if="isFinalAnswer" class="msg-final" ref="cardEl"
       @mouseover="handleMouseOver" @mouseout="handleMouseOut" @click="handleRefClick">
    <div class="msg-header">
      <div class="avatar avatar-ai">AI</div>
      <span class="sender-name">最终汇总</span>
      <span v-if="isStreaming" class="final-badge streaming-badge">输出中...</span>
      <span v-else class="final-badge">完成</span>
      <span v-if="!isStreaming && elapsed" class="meta-info">{{ elapsed }}s</span>
      <span v-if="!isStreaming && estTokens" class="meta-info">~{{ formatTokens(estTokens) }} tok</span>
      <span class="msg-time">{{ timeAgo }}</span>
      <!-- 操作按钮 -->
      <div v-if="!isStreaming" class="msg-actions">
        <button class="action-btn" @click="copyAsText" :title="copySuccess ? '已复制' : '复制文本'">
          {{ copySuccess ? '✓ 已复制' : '📋 复制' }}
        </button>
        <button class="action-btn" @click="exportWord" :disabled="exporting">
          {{ exporting ? '导出中...' : '📄 Word' }}
        </button>
      </div>
    </div>
    <div class="msg-content markdown-body">
      <div v-html="renderedContent"></div>
      <span v-if="isStreaming" class="streaming-cursor"></span>
    </div>
    <!-- 引用来源列表 -->
    <div v-if="references.length > 0 && !isStreaming" class="ref-sources">
      <div class="ref-sources-title">📚 引用来源</div>
      <div v-for="ref in references" :key="ref.id" class="ref-source-item">
        <span class="ref-source-id">[{{ ref.id }}]</span>
        <a :href="ref.url" target="_blank" class="ref-source-link">{{ ref.title }}</a>
      </div>
    </div>
    <!-- 浮动 tooltip -->
    <Teleport to="body">
      <div v-if="tooltipVisible" class="ref-tooltip"
           :style="{ left: tooltipX + 'px', top: tooltipY + 'px' }">
        <div class="ref-tooltip-title">{{ tooltipTitle }}</div>
        <div class="ref-tooltip-snippet">{{ tooltipSnippet }}</div>
        <div v-if="tooltipUrl" class="ref-tooltip-url">🔗 点击角标打开链接</div>
      </div>
    </Teleport>
  </div>

  <!-- 兜底 -->
  <div v-else class="msg-default">
    <div class="msg-header">
      <div class="avatar avatar-default">{{ (message.sender || 'S').charAt(0).toUpperCase() }}</div>
      <span class="sender-name">{{ message.sender }}</span>
      <span class="msg-time">{{ timeAgo }}</span>
      <div v-if="isTaskResult && !isStreaming" class="msg-actions">
        <button class="action-btn" @click="copyAsText" :title="copySuccess ? '已复制' : '复制文本'">
          {{ copySuccess ? '✓ 已复制' : '📋 复制' }}
        </button>
        <button class="action-btn" @click="exportWord" :disabled="exporting">
          {{ exporting ? '导出中...' : '📄 Word' }}
        </button>
      </div>
    </div>
    <div class="msg-content markdown-body">
      <div v-html="renderedContent"></div>
      <span v-if="isStreaming" class="streaming-cursor"></span>
    </div>
  </div>
</template>

<style>
/* ====== 消息通用 ====== */
.msg-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  color: white;
  flex-shrink: 0;
}

.avatar-user { background: linear-gradient(135deg, #5E5CE6, #AF52DE); }
.avatar-lead { background: linear-gradient(135deg, #FF3B30, #FF9500); }
.avatar-ai { background: linear-gradient(135deg, #007AFF, #5AC8FA); }
.avatar-default { background: #8E8E93; }

.sender-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.msg-time {
  font-size: 12px;
  color: var(--text-light);
}

.msg-content {
  margin-left: 40px;
}

/* ====== 统计信息 ====== */
.meta-info {
  font-size: 11px;
  color: var(--text-light);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

/* ====== 状态消息 ====== */
.msg-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 28px;
}

.msg-status-done {
  padding: 8px 28px;
  background: rgba(52, 199, 89, 0.04);
}

.status-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--accent);
  opacity: 0.4;
  flex-shrink: 0;
}

.status-done-dot {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: rgba(52, 199, 89, 0.15);
  color: var(--accent-green);
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.status-text {
  font-size: 12px;
  color: var(--text-muted);
}

.msg-status-done .status-text {
  color: var(--accent-green);
  font-weight: 500;
}

.skill-tag {
  display: inline-flex;
  align-items: center;
  font-size: 10px;
  font-weight: 500;
  padding: 1px 8px;
  border-radius: 20px;
  background: rgba(0, 122, 255, 0.08);
  color: var(--accent);
  white-space: nowrap;
  flex-shrink: 0;
}

.status-text strong {
  color: var(--text-secondary);
  font-weight: 500;
}

/* ====== 用户消息 ====== */
.msg-user {
  padding: 20px 28px;
  background: var(--bg-secondary);
}

.user-text {
  font-size: 15px;
  line-height: 1.65;
  color: var(--text-primary);
}

.user-msg-time {
  margin-left: auto;
}

.user-msg-actions {
  margin-left: 0;
}

/* ====== 思考过程 ====== */
.msg-thinking {
  padding: 20px 28px;
  border-bottom: 1px solid var(--border);
}

.thinking-badge {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 10px;
  border-radius: 20px;
  background: rgba(52, 199, 89, 0.1);
  color: var(--accent-green);
}

.thinking-content {
  color: var(--text-muted) !important;
  font-size: 13px !important;
}

.thinking-content strong {
  color: var(--text-secondary) !important;
}

/* ====== 专家结果 ====== */
.msg-expert {
  padding: 4px 28px;
  overflow: hidden;
}

.expert-toggle {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 0;
  border: none;
  background: none;
  cursor: pointer;
  text-align: left;
  min-width: 0;
}

.toggle-arrow {
  color: var(--text-light);
  transition: transform 0.2s;
  flex-shrink: 0;
  display: flex;
}

.toggle-arrow.open {
  transform: rotate(90deg);
}

.expert-avatar {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  background: var(--bg-secondary);
  color: var(--accent);
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.expert-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.expert-badge {
  font-size: 10px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 20px;
  background: rgba(52, 199, 89, 0.1);
  color: var(--accent-green);
  flex-shrink: 0;
}

.expert-char-count {
  font-size: 11px;
  color: var(--text-light);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

.expert-preview {
  font-size: 12px;
  color: var(--text-light);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  min-width: 0;
}

.expert-content {
  margin-left: 44px;
  padding: 12px 0 12px 16px;
  border-left: 2px solid var(--border);
}

/* 搜索标签 */
.search-tag {
  font-size: 12px;
  flex-shrink: 0;
  cursor: help;
}

/* 网页读取标签 */
.url-read-tag {
  font-size: 12px;
  flex-shrink: 0;
  cursor: help;
}

/* iMessage 标签 */
.imessage-tag {
  font-size: 12px;
  flex-shrink: 0;
  cursor: help;
}

/* Round 标签 */
.round-label {
  font-size: 10px;
  font-weight: 500;
  padding: 1px 7px;
  border-radius: 20px;
  background: rgba(88, 86, 214, 0.1);
  color: #5856D6;
  flex-shrink: 0;
}

.round-label-r1 {
  background: rgba(0, 122, 255, 0.08);
  color: var(--accent);
}

/* 协作讨论卡片样式 */
.msg-expert-discuss {
  border-left: 3px solid rgba(88, 86, 214, 0.3);
  background: rgba(88, 86, 214, 0.02);
}

.expert-avatar-discuss {
  background: rgba(88, 86, 214, 0.1) !important;
  color: #5856D6 !important;
  font-size: 13px !important;
}

.msg-expert-discuss .expert-content {
  border-left-color: rgba(88, 86, 214, 0.3);
}

/* ====== 终止状态 ====== */
.msg-status-stopped {
  padding: 8px 28px;
  background: rgba(255, 149, 0, 0.04);
}

.msg-status-stopped .status-text {
  color: #FF9500;
  font-weight: 500;
}

.status-stopped-dot {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: rgba(255, 149, 0, 0.15);
  color: #FF9500;
  font-size: 8px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

/* ====== 错误消息 ====== */
.msg-error {
  padding: 20px 28px;
  background: rgba(255, 59, 48, 0.04);
  border-left: 3px solid rgba(255, 59, 48, 0.4);
}

.avatar-error {
  background: linear-gradient(135deg, #FF3B30, #FF6961);
  font-size: 14px;
  font-weight: 800;
}

.error-badge {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 10px;
  border-radius: 20px;
  background: rgba(255, 59, 48, 0.1);
  color: #FF3B30;
}

.error-text {
  font-size: 14px;
  line-height: 1.65;
  color: #FF3B30;
}

/* 错误完成状态 */
.msg-status-error {
  background: rgba(255, 59, 48, 0.04) !important;
}

.msg-status-error .status-text {
  color: #FF3B30 !important;
}

.status-error-dot {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: rgba(255, 59, 48, 0.15);
  color: #FF3B30;
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

/* ====== 信息补充卡片 ====== */
.msg-info-card {
  padding: 20px 28px;
  background: linear-gradient(180deg, rgba(255, 149, 0, 0.04) 0%, transparent 100%);
  border-left: 3px solid rgba(255, 149, 0, 0.4);
}

.info-badge {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 10px;
  border-radius: 20px;
  background: rgba(255, 149, 0, 0.1);
  color: #FF9500;
}

.info-badge-done {
  background: rgba(52, 199, 89, 0.1) !important;
  color: var(--accent-green) !important;
}

.info-message {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 16px;
  line-height: 1.5;
}

.info-fields {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.info-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.field-required {
  color: #FF3B30;
  margin-left: 2px;
}

.field-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.option-btn {
  padding: 6px 14px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.option-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: rgba(0, 122, 255, 0.04);
}

.option-btn.selected {
  border-color: var(--accent);
  background: rgba(0, 122, 255, 0.1);
  color: var(--accent);
  font-weight: 500;
}

.field-text {
  width: 100%;
}

.text-input {
  width: 100%;
  padding: 8px 12px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s;
}

.text-input:focus {
  border-color: var(--accent);
}

.text-input::placeholder {
  color: var(--text-light);
}

.info-submit-btn {
  margin-top: 16px;
  padding: 8px 24px;
  border-radius: var(--radius-md);
  border: none;
  background: var(--bg-tertiary);
  color: var(--text-light);
  font-size: 14px;
  font-weight: 500;
  cursor: not-allowed;
  transition: all 0.2s;
}

.info-submit-btn.ready {
  background: var(--accent);
  color: white;
  cursor: pointer;
}

.info-submit-btn.ready:hover {
  opacity: 0.85;
}

.info-submitted-summary {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 16px;
  border-radius: var(--radius-md);
  background: rgba(52, 199, 89, 0.06);
}

.submitted-item {
  font-size: 13px;
  color: var(--text-secondary);
}

.submitted-label {
  font-weight: 500;
  color: var(--text-primary);
}

.submitted-value {
  color: var(--accent);
}

/* ====== 最终答案 ====== */
.msg-final {
  padding: 24px 28px;
  background: linear-gradient(180deg, rgba(0, 122, 255, 0.03) 0%, transparent 100%);
  border-top: 1px solid rgba(0, 122, 255, 0.15);
}

.final-badge {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 10px;
  border-radius: 20px;
  background: rgba(52, 199, 89, 0.1);
  color: var(--accent-green);
}

/* ====== 操作按钮 ====== */
.msg-actions {
  display: flex;
  gap: 6px;
  margin-left: auto;
}

.expert-content-actions {
  margin-left: 44px;
  margin-top: 4px;
}

.action-btn {
  padding: 3px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--text-muted);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.action-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--bg-active);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ====== 兜底 ====== */
.msg-default {
  padding: 20px 28px;
  border-bottom: 1px solid var(--border);
}

/* ====== Markdown 渲染 ====== */
.markdown-body {
  font-size: 15px;
  line-height: 1.75;
  color: var(--text-secondary);
  word-break: break-word;
  overflow-wrap: break-word;
  overflow: hidden;
  max-width: 100%;
}

.markdown-body > *:first-child {
  margin-top: 0;
}

.markdown-body > *:last-child {
  margin-bottom: 0;
}

.markdown-body h1,
.markdown-body h2,
.markdown-body h3,
.markdown-body h4 {
  color: var(--text-primary);
  font-weight: 600;
  margin-top: 20px;
  margin-bottom: 10px;
  line-height: 1.4;
  letter-spacing: -0.02em;
}

.markdown-body h1 { font-size: 22px; }
.markdown-body h2 { font-size: 18px; }
.markdown-body h3 { font-size: 16px; }
.markdown-body h4 { font-size: 15px; }

.markdown-body p {
  margin: 10px 0;
}

.markdown-body ul,
.markdown-body ol {
  margin: 10px 0;
  padding-left: 24px;
}

.markdown-body li {
  margin: 6px 0;
}

/* 示例迁移折叠块 */
.markdown-body :deep(.inline-collapse) {
  border: 1px solid #e5e5e5;
  border-radius: 8px;
  padding: 0;
  margin: 10px 0;
  overflow: hidden;
}

.markdown-body :deep(.inline-collapse > summary) {
  list-style: none;
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 600;
  color: #555;
  background: #f8f8f8;
  cursor: pointer;
  user-select: none;
  display: flex;
  align-items: center;
  gap: 6px;
}

.markdown-body :deep(.inline-collapse > summary::before) {
  content: '▶';
  font-size: 10px;
  color: #999;
  transition: transform 0.2s;
  display: inline-block;
}

.markdown-body :deep(.inline-collapse[open] > summary::before) {
  transform: rotate(90deg);
}

.markdown-body :deep(.inline-collapse > summary::-webkit-details-marker) {
  display: none;
}

.markdown-body :deep(.inline-collapse > ul) {
  margin: 0;
  padding: 8px 12px 8px 28px;
  border-top: 1px solid #efefef;
}

.markdown-body li > p {
  margin: 4px 0;
}

.markdown-body strong {
  color: var(--text-primary);
  font-weight: 600;
}

.markdown-body em {
  font-style: italic;
  color: var(--text-secondary);
}

.markdown-body blockquote {
  margin: 14px 0;
  padding: 12px 20px;
  border-left: 3px solid var(--accent);
  background: var(--bg-secondary);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  color: var(--text-secondary);
}

.markdown-body blockquote p {
  margin: 4px 0;
}

.markdown-body code {
  background: var(--bg-secondary);
  padding: 2px 7px;
  border-radius: 5px;
  font-size: 13px;
  font-family: 'SF Mono', 'Fira Code', 'Menlo', monospace;
  color: var(--accent-red);
}

.markdown-body pre {
  background: var(--bg-secondary);
  padding: 16px 20px;
  border-radius: var(--radius-md);
  overflow-x: auto;
  margin: 14px 0;
  border: 1px solid var(--border);
}

.markdown-body pre code {
  background: none;
  padding: 0;
  border-radius: 0;
  font-size: 13px;
  line-height: 1.65;
  color: var(--text-secondary);
}

.markdown-body table {
  width: 100%;
  border-collapse: collapse;
  margin: 14px 0;
  font-size: 14px;
  display: block;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.markdown-body th,
.markdown-body td {
  border: 1px solid var(--border);
  padding: 10px 14px;
  text-align: left;
}

.markdown-body th {
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-weight: 600;
  font-size: 13px;
}

.markdown-body tr:nth-child(even) {
  background: var(--bg-secondary);
}

.markdown-body hr {
  border: none;
  border-top: 1px solid var(--border);
  margin: 20px 0;
}

.markdown-body a {
  color: var(--accent);
  text-decoration: none;
}

.markdown-body a:hover {
  text-decoration: underline;
}

/* ====== 流式输出光标 ====== */
.streaming-cursor {
  display: inline-block;
  width: 2px;
  height: 18px;
  background: var(--accent);
  margin-left: 2px;
  vertical-align: text-bottom;
  animation: blink-cursor 0.8s ease-in-out infinite;
}

@keyframes blink-cursor {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.streaming-badge {
  background: rgba(0, 122, 255, 0.1) !important;
  color: var(--accent) !important;
  animation: pulse-badge 1.5s ease-in-out infinite;
}

@keyframes pulse-badge {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* ====== 引用角标 ====== */
.ref-mark {
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
}

.ref-mark:hover {
  background: rgba(0, 122, 255, 0.12);
  color: #0055cc;
}

/* 引用来源列表 */
.ref-sources {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.ref-sources-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.ref-source-item {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 13px;
  line-height: 1.6;
  margin-bottom: 4px;
}

.ref-source-id {
  color: var(--accent);
  font-weight: 600;
  flex-shrink: 0;
  font-size: 12px;
}

.ref-source-link {
  color: var(--text-secondary);
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ref-source-link:hover {
  color: var(--accent);
  text-decoration: underline;
}

/* 浮动 tooltip */
.ref-tooltip {
  position: fixed;
  transform: translateX(-50%) translateY(-100%);
  max-width: 360px;
  min-width: 200px;
  background: var(--bg-primary, #fff);
  border: 1px solid var(--border, #e0e0e0);
  border-radius: 10px;
  padding: 12px 14px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12), 0 2px 8px rgba(0, 0, 0, 0.06);
  z-index: 9999;
  pointer-events: none;
  animation: tooltip-in 0.15s ease-out;
}

@keyframes tooltip-in {
  from { opacity: 0; transform: translateX(-50%) translateY(-100%) translateY(4px); }
  to   { opacity: 1; transform: translateX(-50%) translateY(-100%); }
}

.ref-tooltip-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 6px;
  line-height: 1.4;
}

.ref-tooltip-snippet {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.ref-tooltip-url {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid var(--border, #e8e8e8);
}
</style>
