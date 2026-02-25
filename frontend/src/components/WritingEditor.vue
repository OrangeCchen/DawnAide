<script setup lang="ts">
/**
 * WritingEditor — 双栏写作编辑器
 *
 * 左栏：MessageCard 同款对话区（markdown 渲染）+ 主界面输入框风格
 * 右栏：Word 风格 contenteditable 纸张 + SelectionToolbar 浮动工具栏
 */
import { ref, computed, nextTick, watch, onMounted } from 'vue'
import MarkdownIt from 'markdown-it'
import { useTeamStore } from '../stores/teamStore'
import SelectionToolbar from './SelectionToolbar.vue'
import { highlightMissing } from '../utils/highlightMissing'

const store = useTeamStore()
const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

// ===== 状态 =====
const docText = ref(store.editorState.content)
const docEditor = ref<HTMLElement>()
const refining = ref(false)
const instruction = ref('')
const inputRef = ref<HTMLTextAreaElement>()
const chatScrollRef = ref<HTMLElement>()
const copySuccess = ref(false)
const exporting = ref(false)
const docFocused = ref(false)

// ===== 对话历史 =====
interface ChatMsg { id: string; role: 'user' | 'assistant'; text: string; streaming?: boolean }
const chatHistory = ref<ChatMsg[]>([
  {
    id: 'welcome',
    role: 'assistant',
    text: '你好！我已加载这篇文稿，可以直接在右侧编辑，也可以告诉我如何修改，例如：\n\n- 把第二段改得更简洁\n- 整体语气改得更正式\n- 在开头加一段引言',
  },
])

// AI 消息的 markdown 渲染（含占位符高亮）
function renderMd(text: string) {
  return highlightMissing(md.render(text))
}

// ===== 初始化右栏 =====
onMounted(() => {
  if (docEditor.value) {
    docEditor.value.innerHTML = highlightMissing(md.render(docText.value))
  }
})

// ===== 实时同步：流式内容 → 右栏 =====
watch(
  () => store.streamTick,
  () => {
    if (!refining.value) return
    const msgs = store.messages[store.editorState.teamId] || []
    for (let i = msgs.length - 1; i >= 0; i--) {
      const m = msgs[i]
      if (m.type === 'task_result' && m.metadata?.refine_result) {
        if (m.content && docEditor.value) {
          const scrollEl = docEditor.value.closest('.doc-scroll') as HTMLElement | null
          const scrollTop = scrollEl?.scrollTop ?? 0
          docEditor.value.innerHTML = highlightMissing(md.render(m.content))
          if (scrollEl) scrollEl.scrollTop = scrollTop
          docText.value = m.content
        }
        break
      }
    }
  }
)

// 流式完成
watch(
  () => store.messages[store.editorState.teamId],
  (msgs) => {
    if (!refining.value || !msgs) return
    for (let i = msgs.length - 1; i >= 0; i--) {
      const m = msgs[i]
      if (m.type === 'task_result' && m.metadata?.refine_result) {
        if (!m.metadata?.streaming) {
          if (m.content) {
            docText.value = m.content
            if (docEditor.value) docEditor.value.innerHTML = highlightMissing(md.render(m.content))
          }
          refining.value = false
          const last = chatHistory.value[chatHistory.value.length - 1]
          if (last?.role === 'assistant' && last.streaming) {
            last.text = '文稿已按指令更新，可继续编辑或再次润色。'
            last.streaming = false
            nextTick(scrollChat)
          }
        }
        return
      }
    }
  },
  { deep: true }
)

// ===== 发送润色指令 =====
async function sendInstruction() {
  const text = instruction.value.trim()
  if (!text || refining.value) return

  instruction.value = ''
  refining.value = true

  if (docEditor.value) docText.value = docEditor.value.innerText

  const uid = Date.now().toString(36)
  chatHistory.value.push({ id: uid, role: 'user', text })
  chatHistory.value.push({ id: uid + '_ai', role: 'assistant', text: '正在修改文稿，请稍候...', streaming: true })

  await nextTick()
  scrollChat()

  try {
    const res = await fetch('/api/refine', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        team_id: store.editorState.teamId,
        current_content: docText.value,
        instruction: text,
        original_task: store.editorState.originalTask,
      }),
    })
    if (!res.ok) {
      refining.value = false
      const last = chatHistory.value[chatHistory.value.length - 1]
      if (last?.streaming) { last.text = '修改失败，请重试。'; last.streaming = false }
    }
  } catch {
    refining.value = false
    const last = chatHistory.value[chatHistory.value.length - 1]
    if (last?.streaming) { last.text = '网络错误，请重试。'; last.streaming = false }
  }
}

// ===== SelectionToolbar 事件处理 =====
function onToolbarExec(cmd: string, val?: string) {
  document.execCommand(cmd, false, val)
  docEditor.value?.focus()
}

function onAiRewrite(selectedText: string) {
  // 将选中文本作为具体修改对象发送润色指令
  instruction.value = `请改写以下这段文字，使其更流畅自然：\n\n"${selectedText}"`
  sendInstruction()
}

// ===== 文档直接编辑 =====
function onDocInput() {
  if (docEditor.value) docText.value = docEditor.value.innerText
}

// 工具栏按钮（顶部固定格式栏）
function execCmd(cmd: string, val?: string) {
  document.execCommand(cmd, false, val)
  docEditor.value?.focus()
}

// 撤销/重做：使用 document.execCommand，保持 contenteditable 焦点
function undoEdit() {
  docEditor.value?.focus()
  document.execCommand('undo')
}

function redoEdit() {
  docEditor.value?.focus()
  document.execCommand('redo')
}

function scrollChat() {
  nextTick(() => {
    if (chatScrollRef.value) {
      chatScrollRef.value.scrollTop = chatScrollRef.value.scrollHeight
    }
  })
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendInstruction()
  }
}

async function copyDoc() {
  const text = docEditor.value?.innerText || docText.value
  try {
    await navigator.clipboard.writeText(text)
    copySuccess.value = true
    setTimeout(() => { copySuccess.value = false }, 2000)
  } catch {}
}

async function exportWordDoc() {
  if (exporting.value) return
  exporting.value = true
  try {
    const res = await fetch('/api/export/word', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: docText.value, title: '文档', doc_type: 'general' }),
    })
    if (res.ok) {
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      const cd = res.headers.get('content-disposition')
      a.href = url
      a.download = cd?.match(/filename=(.+)/)?.[1] || '文档.docx'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    }
  } catch {}
  finally { exporting.value = false }
}

function goBack() {
  store.closeEditor()
}

const sendReady = computed(() => instruction.value.trim().length > 0 && !refining.value)
</script>

<template>
  <div class="editor-root">
    <!-- ===== 顶部导航栏 ===== -->
    <div class="editor-nav">
      <button class="nav-back" @click="goBack">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
          <path d="M10 12L6 8l4-4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        返回对话
      </button>
      <span class="nav-title">写作编辑器</span>
      <div class="nav-actions">
        <button class="nav-btn" @click="copyDoc">
          {{ copySuccess ? '✓ 已复制' : '📋 复制全文' }}
        </button>
        <button class="nav-btn" @click="exportWordDoc" :disabled="exporting">
          {{ exporting ? '导出中...' : '📄 导出 Word' }}
        </button>
      </div>
    </div>

    <!-- ===== 双栏主体 ===== -->
    <div class="editor-body">

      <!-- ========== 左栏：对话润色 ========== -->
      <div class="editor-left">
        <div class="left-header">
          <span class="left-title">AI 润色</span>
          <span class="left-hint">告诉 AI 如何修改，或直接编辑右侧文档</span>
        </div>

        <!-- 对话历史（MessageCard 同款视觉） -->
        <div ref="chatScrollRef" class="chat-messages">
          <!-- 用户消息 — 完全复刻 .msg-user -->
          <div
            v-for="item in chatHistory"
            :key="item.id"
          >
            <div v-if="item.role === 'user'" class="msg-user">
              <div class="msg-header">
                <div class="avatar avatar-user">U</div>
                <span class="sender-name">你</span>
              </div>
              <div class="msg-content user-text">{{ item.text }}</div>
            </div>

            <!-- AI 消息 — 复刻 .msg-final，markdown 渲染 -->
            <div v-else class="msg-ai">
              <div class="msg-header">
                <div class="avatar avatar-lead">AI</div>
                <span class="sender-name">写作助手</span>
                <span v-if="item.streaming" class="badge badge-streaming">输出中</span>
                <span v-else-if="item.id !== 'welcome'" class="badge badge-done">完成</span>
              </div>
              <div
                class="msg-content ai-md"
                :class="{ 'streaming-fade': item.streaming }"
                v-html="renderMd(item.text)"
              ></div>
              <span v-if="item.streaming" class="streaming-cursor-wrap">
                <span class="streaming-cursor"></span>
              </span>
            </div>
          </div>
        </div>

        <!-- 输入区（主界面 input-box 同款） -->
        <div class="input-area">
          <div class="input-box" :class="{ 'input-box-focus': instruction.length > 0 && !refining }">
            <textarea
              ref="inputRef"
              v-model="instruction"
              @keydown="handleKeydown"
              :placeholder="refining ? '正在修改中，请稍候...' : '描述修改要求（Enter 发送，Shift+Enter 换行）'"
              :disabled="refining"
              rows="1"
              class="main-textarea"
            ></textarea>
            <button
              class="btn-send"
              :class="{ ready: sendReady }"
              :disabled="!sendReady"
              @click="sendInstruction"
            >
              <svg v-if="!refining" width="14" height="14" viewBox="0 0 16 16" fill="none">
                <path d="M14 2L7.5 8.5M14 2l-4.5 12-2-5.5L2 6.5 14 2z" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              <svg v-else width="14" height="14" viewBox="0 0 16 16" fill="none" class="spin-icon">
                <circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="18 10" stroke-linecap="round"/>
              </svg>
            </button>
          </div>
        </div>
      </div>

      <!-- 分隔线 -->
      <div class="editor-divider"></div>

      <!-- ========== 右栏：Word 风格文档 ========== -->
      <div class="editor-right">
        <!-- 文档工具栏 -->
        <div class="doc-toolbar">
          <button class="toolbar-btn tb-bold"   data-tip="粗体 (⌘B)"    @mousedown.prevent="execCmd('bold')"><strong>B</strong></button>
          <button class="toolbar-btn tb-strike" data-tip="删除线"         @mousedown.prevent="execCmd('strikethrough')"><s>S</s></button>
          <button class="toolbar-btn tb-italic" data-tip="斜体 (⌘I)"    @mousedown.prevent="execCmd('italic')"><em>I</em></button>
          <button class="toolbar-btn tb-under"  data-tip="下划线 (⌘U)"  @mousedown.prevent="execCmd('underline')"><u>U</u></button>
          <div class="toolbar-sep"></div>
          <button class="toolbar-btn" data-tip="无序列表" @mousedown.prevent="execCmd('insertUnorderedList')">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="2.5" cy="4" r="1.2" fill="currentColor"/><circle cx="2.5" cy="8" r="1.2" fill="currentColor"/><circle cx="2.5" cy="12" r="1.2" fill="currentColor"/><line x1="6" y1="4" x2="15" y2="4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><line x1="6" y1="8" x2="15" y2="8" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><line x1="6" y1="12" x2="15" y2="12" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>
          </button>
          <button class="toolbar-btn" data-tip="有序列表" @mousedown.prevent="execCmd('insertOrderedList')">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><text x="0.5" y="5.5" font-size="5" fill="currentColor" font-family="monospace">1.</text><text x="0.5" y="9.5" font-size="5" fill="currentColor" font-family="monospace">2.</text><text x="0.5" y="13.5" font-size="5" fill="currentColor" font-family="monospace">3.</text><line x1="6" y1="4" x2="15" y2="4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><line x1="6" y1="8" x2="15" y2="8" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><line x1="6" y1="12" x2="15" y2="12" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>
          </button>
          <div class="toolbar-sep"></div>
          <button class="toolbar-btn" data-tip="二级标题" @mousedown.prevent="execCmd('formatBlock', 'h2')">H2</button>
          <button class="toolbar-btn" data-tip="三级标题" @mousedown.prevent="execCmd('formatBlock', 'h3')">H3</button>
          <button class="toolbar-btn" data-tip="正文段落" @mousedown.prevent="execCmd('formatBlock', 'p')">¶</button>
          <div class="toolbar-sep"></div>
          <button class="toolbar-btn" data-tip="撤销 (⌘Z)"   @mousedown.prevent="undoEdit">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M3 7H10a3 3 0 010 6H7" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M3 7L6 4M3 7l3 3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
          <button class="toolbar-btn" data-tip="重做 (⌘⇧Z)" @mousedown.prevent="redoEdit">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M13 7H6a3 3 0 000 6h3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M13 7l-3-3M13 7l-3 3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
          <div class="toolbar-right">
            <span v-if="refining" class="doc-updating">
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" class="spin-icon" style="margin-right:4px">
                <circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="18 10" stroke-linecap="round"/>
              </svg>
              AI 更新中...
            </span>
          </div>
        </div>

        <!-- Word 纸张区域 -->
        <div class="doc-scroll">
          <div class="doc-page-wrapper">
            <div
              ref="docEditor"
              class="doc-page"
              :contenteditable="!refining"
              @input="onDocInput"
              @focus="docFocused = true"
              @blur="docFocused = false"
              spellcheck="false"
            ></div>
          </div>
        </div>
      </div>
    </div>

    <!-- ===== 选中浮动工具栏（Teleport 到 body） ===== -->
    <SelectionToolbar
      :target-el="docEditor ?? null"
      @exec="onToolbarExec"
      @ai-rewrite="onAiRewrite"
    />
  </div>
</template>

<style scoped>
/* ===== 根容器 ===== */
.editor-root {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-secondary);
  overflow: hidden;
}

/* ===== 顶部导航 ===== */
.editor-nav {
  height: 52px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  padding: 0 24px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-card);
  gap: 16px;
}

.nav-back {
  display: flex;
  align-items: center;
  gap: 5px;
  border: none;
  background: none;
  color: var(--accent);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  transition: background 0.15s;
  flex-shrink: 0;
}
.nav-back:hover { background: var(--bg-active); }

.nav-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.02em;
  flex: 1;
  text-align: center;
}

.nav-actions { display: flex; gap: 8px; flex-shrink: 0; }

.nav-btn {
  padding: 4px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-card);
  color: var(--text-muted);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.nav-btn:hover { border-color: var(--accent); color: var(--accent); background: var(--bg-active); }
.nav-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* ===== 双栏 ===== */
.editor-body {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
}

/* ===== 左栏 ===== */
.editor-left {
  width: 320px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg-card);
  min-height: 0;
  border-right: 1px solid var(--border);
}

.left-header {
  padding: 14px 28px 12px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.left-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  display: block;
  letter-spacing: -0.01em;
}

.left-hint {
  font-size: 11px;
  color: var(--text-light);
  margin-top: 3px;
  display: block;
  line-height: 1.45;
}

/* ===== 对话历史（复刻 ChatArea .chat-messages） ===== */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

/* ----- 用户消息 — 完全复刻 MessageCard .msg-user ----- */
.msg-user {
  padding: 16px 28px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
}

/* ----- AI 消息 — 完全复刻 MessageCard .msg-final ----- */
.msg-ai {
  padding: 16px 28px 14px;
  background: linear-gradient(180deg, rgba(0, 122, 255, 0.03) 0%, transparent 100%);
  border-bottom: 1px solid var(--border);
  position: relative;
}

/* ----- 消息头部 — 复刻 .msg-header ----- */
.msg-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.avatar {
  width: 26px;
  height: 26px;
  border-radius: 7px;
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.avatar-user {
  background: linear-gradient(135deg, #5E5CE6, #AF52DE);
  color: white;
}

.avatar-lead {
  background: linear-gradient(135deg, #007AFF, #5AC8FA);
  color: white;
}

.sender-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

/* ----- 徽章 — 复刻 MessageCard ----- */
.badge {
  font-size: 10px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 20px;
}

.badge-streaming {
  background: rgba(0, 122, 255, 0.1);
  color: var(--accent);
  animation: pulse-badge 1.4s ease-in-out infinite;
}

.badge-done {
  background: rgba(52, 199, 89, 0.1);
  color: var(--accent-green);
}

@keyframes pulse-badge {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.45; }
}

/* ----- 消息内容区 ----- */
.msg-content { margin-left: 36px; }

.user-text {
  font-size: 14px;
  line-height: 1.65;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}

/* AI 消息 markdown 渲染区域 — 完全复刻 MessageCard .markdown-body */
.ai-md {
  font-size: 14px;
  line-height: 1.75;
  color: var(--text-secondary);
  word-break: break-word;
  overflow-wrap: break-word;
}

.streaming-fade { color: var(--text-muted); }

/* 流式光标 */
.streaming-cursor-wrap {
  display: block;
  margin-left: 36px;
  margin-top: 2px;
}

.streaming-cursor {
  display: inline-block;
  width: 2px;
  height: 15px;
  background: var(--accent);
  vertical-align: text-bottom;
  animation: blink-cursor 0.8s ease-in-out infinite;
}

@keyframes blink-cursor {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

/* ===== 输入区（完全复刻 ChatArea .input-box） ===== */
.input-area {
  flex-shrink: 0;
  padding: 10px 16px 14px;
  border-top: 1px solid var(--border);
  background: var(--bg-card);
}

.input-box {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 8px 10px 8px 14px;
  border-radius: var(--radius-lg);
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.input-box:focus-within,
.input-box-focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.08);
}

.main-textarea {
  flex: 1;
  resize: none;
  border: none;
  background: transparent;
  outline: none;
  font-size: 13px;
  line-height: 1.55;
  color: var(--text-primary);
  min-height: 20px;
  max-height: 80px;
  overflow-y: auto;
}

.main-textarea::placeholder { color: var(--text-light); }
.main-textarea:disabled { cursor: not-allowed; }

.btn-send {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  border: none;
  background: var(--bg-tertiary);
  color: var(--text-light);
  cursor: not-allowed;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.2s;
}

.btn-send.ready { background: var(--accent); color: white; cursor: pointer; }
.btn-send.ready:hover { opacity: 0.85; }

@keyframes spin { to { transform: rotate(360deg); } }
.spin-icon { animation: spin 1s linear infinite; }

/* ===== 分隔线 ===== */
.editor-divider {
  width: 1px;
  background: var(--border);
  flex-shrink: 0;
}

/* ===== 右栏 ===== */
.editor-right {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  background: #e8e8e8;
}

/* 文档工具栏 */
.doc-toolbar {
  flex-shrink: 0;
  height: 36px;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 0 16px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
}

.toolbar-btn {
  min-width: 28px;
  height: 26px;
  padding: 0 6px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.toolbar-btn:hover { background: var(--bg-secondary); color: var(--text-primary); }
.toolbar-btn:active { background: var(--bg-active); color: var(--accent); }

.tb-bold   { font-weight: 700; }
.tb-italic { font-style: italic; }
.tb-under  { text-decoration: underline; }
.tb-strike { text-decoration: line-through; }

/* data-tip tooltip — 出现在按钮下方 */
.toolbar-btn[data-tip] { position: relative; overflow: visible; }

.toolbar-btn[data-tip]::after {
  content: attr(data-tip);
  position: absolute;
  top: calc(100% + 6px);
  left: 50%;
  transform: translateX(-50%);
  background: rgba(28, 28, 30, 0.88);
  color: #fff;
  font-size: 11px;
  font-weight: 400;
  padding: 4px 8px;
  border-radius: 5px;
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.15s;
  z-index: 200;
  letter-spacing: 0;
  line-height: 1.4;
}

.toolbar-btn[data-tip]:hover::after {
  opacity: 1;
  transition-delay: 0.3s;
}

.toolbar-sep {
  width: 1px;
  height: 18px;
  background: var(--border);
  margin: 0 4px;
  flex-shrink: 0;
}

.toolbar-right {
  flex: 1;
  display: flex;
  justify-content: flex-end;
  align-items: center;
}

.doc-updating {
  display: flex;
  align-items: center;
  font-size: 12px;
  color: var(--accent);
  font-weight: 500;
}

/* Word 纸张区域 */
.doc-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 32px 24px;
  min-height: 0;
}

.doc-page-wrapper {
  max-width: 860px;
  margin: 0 auto;
}

.doc-page {
  background: #ffffff;
  border-radius: 2px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.12), 0 4px 16px rgba(0,0,0,0.08);
  padding: 60px 72px;
  min-height: 1100px;
  outline: none;
  cursor: text;
  caret-color: var(--accent);
  font-family: 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'SimSun', Georgia, serif;
  font-size: 15px;
  line-height: 1.9;
  color: #1a1a1a;
  word-break: break-word;
  overflow-wrap: break-word;
  transition: box-shadow 0.2s;
}

.doc-page:focus {
  box-shadow: 0 2px 8px rgba(0,0,0,0.15), 0 8px 32px rgba(0,0,0,0.1), 0 0 0 2px rgba(0, 122, 255, 0.15);
}

.doc-page[contenteditable="false"] {
  cursor: default;
  opacity: 0.92;
}
</style>

<!-- markdown-body 样式（非 scoped，作用于 .ai-md 内部）-->
<style>
/* ===== 占位符高亮（全局，左右栏通用） ===== */
mark.info-missing {
  background: rgba(255, 59, 48, 0.1);
  color: #FF3B30;
  border: 1px solid rgba(255, 59, 48, 0.25);
  border-radius: 4px;
  padding: 1px 5px;
  font-weight: 600;
  font-style: normal;
  cursor: pointer;
  white-space: nowrap;
  font-size: inherit;
  /* 取消浏览器默认 mark 背景色 */
  -webkit-text-fill-color: #FF3B30;
}

mark.info-missing:hover {
  background: rgba(255, 59, 48, 0.18);
  border-color: rgba(255, 59, 48, 0.45);
}

/* doc-page 中的占位符（纸张上红色更醒目） */
.doc-page mark.info-missing {
  background: rgba(255, 59, 48, 0.08);
  color: #D32F2F;
  -webkit-text-fill-color: #D32F2F;
  font-weight: 700;
  border: 1.5px solid rgba(211, 47, 47, 0.3);
  border-radius: 3px;
}

/* 左栏 AI 消息 markdown 样式 — 复刻 MessageCard .markdown-body */
.ai-md > *:first-child { margin-top: 0; }
.ai-md > *:last-child  { margin-bottom: 0; }

.ai-md h1, .ai-md h2, .ai-md h3, .ai-md h4 {
  color: var(--text-primary);
  font-weight: 600;
  margin-top: 14px;
  margin-bottom: 6px;
  line-height: 1.4;
}
.ai-md h1 { font-size: 18px; }
.ai-md h2 { font-size: 15px; }
.ai-md h3 { font-size: 14px; }

.ai-md p { margin: 6px 0; }

.ai-md ul { margin: 6px 0; padding-left: 20px; list-style-type: disc; }
.ai-md ol { margin: 6px 0; padding-left: 20px; list-style-type: decimal; }
.ai-md ul ul { list-style-type: circle; }
.ai-md ul ul ul { list-style-type: square; }
.ai-md li { margin: 4px 0; display: list-item; }

.ai-md strong { color: var(--text-primary); font-weight: 600; }
.ai-md em    { font-style: italic; }

.ai-md code {
  background: var(--bg-secondary);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 12px;
  font-family: 'SF Mono', 'Menlo', monospace;
  color: var(--accent-red);
}

.ai-md blockquote {
  margin: 8px 0;
  padding: 8px 14px;
  border-left: 2px solid var(--accent);
  background: var(--bg-secondary);
  border-radius: 0 4px 4px 0;
  color: var(--text-secondary);
}

/* 右栏 doc-page 文档 markdown 样式 */
.doc-page h1, .doc-page h2, .doc-page h3, .doc-page h4 {
  font-family: 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
  font-weight: 700;
  color: #111;
  line-height: 1.4;
  margin-top: 28px;
  margin-bottom: 12px;
  letter-spacing: -0.01em;
}
.doc-page h1 { font-size: 26px; }
.doc-page h2 { font-size: 20px; border-bottom: 1.5px solid #e0e0e0; padding-bottom: 6px; }
.doc-page h3 { font-size: 17px; }
.doc-page h4 { font-size: 15px; }

.doc-page p { margin: 12px 0; color: #222; }
.doc-page ul { margin: 12px 0; padding-left: 26px; list-style-type: disc; }
.doc-page ol { margin: 12px 0; padding-left: 26px; list-style-type: decimal; }
.doc-page ul ul { list-style-type: circle; }
.doc-page li { margin: 6px 0; color: #222; display: list-item; }
.doc-page strong { font-weight: 700; color: #111; }
.doc-page em { font-style: italic; color: #333; }
.doc-page u { text-decoration: underline; text-underline-offset: 2px; }

.doc-page blockquote {
  margin: 16px 0;
  padding: 12px 20px;
  border-left: 3px solid #007AFF;
  background: #f5f8ff;
  border-radius: 0 6px 6px 0;
  color: #444;
}
.doc-page blockquote p { margin: 4px 0; }

.doc-page code {
  background: #f3f4f6;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  font-family: 'SF Mono', 'Fira Code', 'Menlo', monospace;
  color: #d14;
}

.doc-page pre {
  background: #f3f4f6;
  padding: 14px 18px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 16px 0;
  border: 1px solid #e5e5e5;
}
.doc-page pre code { background: none; padding: 0; color: #333; font-size: 13px; line-height: 1.65; }

.doc-page table { width: 100%; border-collapse: collapse; margin: 14px 0; font-size: 14px; }
.doc-page th, .doc-page td { border: 1px solid #e0e0e0; padding: 10px 14px; text-align: left; }
.doc-page th { background: #f8f8f8; font-weight: 600; color: #222; }
.doc-page tr:nth-child(even) td { background: #fafafa; }

.doc-page hr { border: none; border-top: 1.5px solid #e0e0e0; margin: 24px 0; }
.doc-page a { color: #007AFF; text-decoration: none; }
.doc-page a:hover { text-decoration: underline; }

.doc-page > *:first-child { margin-top: 0; }
.doc-page > *:last-child  { margin-bottom: 0; }
</style>
