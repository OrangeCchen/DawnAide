<script setup lang="ts">
/**
 * SelectionToolbar — 右键选中文本时浮现的快捷工具栏
 *
 * 设计参考豆包的选中工具栏：AI 改写 + 常用格式 + 扩展预留
 *
 * 使用方式：
 *   <SelectionToolbar :target-el="docEditorRef" @ai-rewrite="..." @exec="..." />
 *
 * Props:
 *   targetEl — 监听选区的 contenteditable 元素
 *
 * Emits:
 *   ai-rewrite(text)   — 用户点击「AI 改写」，携带选中文本
 *   exec(cmd, val?)    — 执行 document.execCommand 指令
 *   copy-selection()   — 复制选中文本
 */

import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'

const props = defineProps<{
  targetEl: HTMLElement | null
}>()

const emit = defineEmits<{
  (e: 'ai-rewrite', text: string): void
  (e: 'exec', cmd: string, val?: string): void
  (e: 'copy-selection'): void
}>()

// ===== 状态 =====
const visible = ref(false)
const position = ref({ top: 0, left: 0 })
const selectedText = ref('')
const toolbarRef = ref<HTMLElement>()
const copyDone = ref(false)

// ===== 选区监听 =====
let selTimer: ReturnType<typeof setTimeout> | null = null

function onSelectionChange() {
  if (selTimer) clearTimeout(selTimer)
  selTimer = setTimeout(updateToolbar, 80)
}

async function updateToolbar() {
  const sel = window.getSelection()

  if (!sel || sel.isCollapsed || !sel.rangeCount) {
    visible.value = false
    return
  }

  const range = sel.getRangeAt(0)
  const text = sel.toString().trim()

  if (!text) {
    visible.value = false
    return
  }

  // 仅在目标元素内的选区才显示
  if (props.targetEl && !props.targetEl.contains(range.commonAncestorContainer)) {
    visible.value = false
    return
  }

  const rect = range.getBoundingClientRect()
  if (!rect.width && !rect.height) {
    visible.value = false
    return
  }

  selectedText.value = text
  visible.value = true

  // 先渲染，再精确定位
  await nextTick()
  positionToolbar(rect)
}

function positionToolbar(selRect: DOMRect) {
  const toolbar = toolbarRef.value
  if (!toolbar) return

  const tw = toolbar.offsetWidth  || 460
  const th = toolbar.offsetHeight || 40
  const gap = 10

  // 水平：以选区中心为准，限制在视口内
  let left = selRect.left + selRect.width / 2 - tw / 2
  left = Math.max(8, Math.min(left, window.innerWidth - tw - 8))

  // 垂直：优先显示在选区上方；空间不足则显示在下方
  let top = selRect.top - th - gap
  if (top < 8) top = selRect.bottom + gap

  position.value = { top, left }
}

// ===== 点击外部关闭 =====
function onMousedown(e: MouseEvent) {
  // 如果点击的不是 toolbar，就不做任何事（selectionchange 会自然触发关闭）
  if (toolbarRef.value && toolbarRef.value.contains(e.target as Node)) {
    // 阻止 mousedown 取消选区（否则点击按钮时选区会消失）
    e.preventDefault()
  }
}

onMounted(() => {
  document.addEventListener('selectionchange', onSelectionChange)
  document.addEventListener('mousedown', onMousedown)
})

onBeforeUnmount(() => {
  document.removeEventListener('selectionchange', onSelectionChange)
  document.removeEventListener('mousedown', onMousedown)
  if (selTimer) clearTimeout(selTimer)
})

// ===== 操作 =====
function execCmd(cmd: string, val?: string) {
  emit('exec', cmd, val)
}

function aiRewrite() {
  emit('ai-rewrite', selectedText.value)
  visible.value = false
}

async function copySelection() {
  try {
    await navigator.clipboard.writeText(selectedText.value)
    copyDone.value = true
    emit('copy-selection')
    setTimeout(() => { copyDone.value = false }, 1800)
  } catch {}
}

// ===== 工具项定义（方便后续扩展） =====
interface ToolItem {
  type: 'btn' | 'sep'
  id?: string
  label?: string
  title?: string
  icon?: string
  action?: () => void
}

const tools: ToolItem[] = [
  // 格式
  { type: 'btn', id: 'bold',          label: 'B',  title: '粗体 (⌘B)',      icon: 'bold',          action: () => execCmd('bold') },
  { type: 'btn', id: 'strikethrough', label: 'S',  title: '删除线',          icon: 'strike',        action: () => execCmd('strikethrough') },
  { type: 'btn', id: 'italic',        label: 'I',  title: '斜体 (⌘I)',      icon: 'italic',        action: () => execCmd('italic') },
  { type: 'btn', id: 'underline',     label: 'U',  title: '下划线 (⌘U)',    icon: 'underline',     action: () => execCmd('underline') },
  { type: 'sep' },
  { type: 'btn', id: 'link',          label: '🔗', title: '插入链接',        icon: 'link',          action: insertLink },
  { type: 'btn', id: 'code',          label: '</>',title: '行内代码',        icon: 'code',          action: () => wrapInlineCode() },
  { type: 'sep' },
  { type: 'btn', id: 'copy',          label: copyDone.value ? '✓' : '⎘', title: '复制选中内容', icon: 'copy', action: copySelection },
]
// 让 copyDone 响应式驱动 label
function getCopyLabel() { return copyDone.value ? '✓ 已复制' : '⎘ 复制' }

function insertLink() {
  const url = window.prompt('输入链接地址：', 'https://')
  if (url) execCmd('createLink', url)
}

function wrapInlineCode() {
  const sel = window.getSelection()
  if (!sel || !sel.rangeCount) return
  const range = sel.getRangeAt(0)
  const text = range.toString()
  if (!text) return
  const code = document.createElement('code')
  code.textContent = text
  range.deleteContents()
  range.insertNode(code)
  // 清除选区
  sel.removeAllRanges()
  visible.value = false
}
</script>

<template>
  <Teleport to="body">
    <Transition name="toolbar-pop">
      <div
        v-if="visible"
        ref="toolbarRef"
        class="selection-toolbar"
        :style="{ top: position.top + 'px', left: position.left + 'px' }"
      >
        <!-- AI 改写 — 核心入口，突出显示 -->
        <button class="tb-ai-btn" data-tip="AI 改写选中内容" @click="aiRewrite">
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" style="flex-shrink:0">
            <path d="M3 8c0-2.76 2.24-5 5-5s5 2.24 5 5-2.24 5-5 5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
            <path d="M8 5v3l2 1.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          AI 改写
        </button>

        <div class="tb-sep"></div>

        <!-- 格式按钮组 -->
        <button class="tb-btn tb-bold"   data-tip="粗体"   @click="execCmd('bold')"><strong>B</strong></button>
        <button class="tb-btn tb-strike" data-tip="删除线" @click="execCmd('strikethrough')"><s>S</s></button>
        <button class="tb-btn tb-italic" data-tip="斜体"   @click="execCmd('italic')"><em>I</em></button>
        <button class="tb-btn tb-under"  data-tip="下划线" @click="execCmd('underline')"><u>U</u></button>

        <div class="tb-sep"></div>

        <!-- 链接 -->
        <button class="tb-btn" data-tip="插入链接" @click="insertLink">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
            <path d="M6.5 9.5a3.5 3.5 0 005 0l2-2a3.5 3.5 0 00-5-5l-1 1" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
            <path d="M9.5 6.5a3.5 3.5 0 00-5 0l-2 2a3.5 3.5 0 005 5l1-1" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
          </svg>
        </button>

        <!-- 行内代码 -->
        <button class="tb-btn tb-code" data-tip="行内代码" @click="wrapInlineCode">&lt;/&gt;</button>

        <div class="tb-sep"></div>

        <!-- 复制 -->
        <button class="tb-btn" :data-tip="copyDone ? '已复制！' : '复制选中内容'" @click="copySelection">
          <svg v-if="!copyDone" width="14" height="14" viewBox="0 0 16 16" fill="none">
            <rect x="5" y="4" width="8" height="10" rx="1.5" stroke="currentColor" stroke-width="1.3"/>
            <path d="M3 12V3a1 1 0 011-1h7" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
          </svg>
          <svg v-else width="14" height="14" viewBox="0 0 16 16" fill="none">
            <path d="M3 8.5l3.5 3.5 6.5-7" stroke="#34C759" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>

        <!-- 预留扩展槽（未来可插入：批注、高亮、翻译等） -->
        <!-- <slot name="extra-tools" /> -->

        <!-- 小箭头 -->
        <div class="tb-arrow"></div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.selection-toolbar {
  position: fixed;
  z-index: 9000;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 5px 8px;
  background: #1c1c1e;
  border-radius: 10px;
  box-shadow:
    0 4px 16px rgba(0, 0, 0, 0.28),
    0 1px 4px rgba(0, 0, 0, 0.2);
  pointer-events: auto;
  user-select: none;
  white-space: nowrap;
}

/* AI 改写按钮 */
.tb-ai-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border-radius: 6px;
  border: none;
  background: linear-gradient(135deg, #5E5CE6, #007AFF);
  color: white;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s, transform 0.1s;
  letter-spacing: 0.01em;
}
.tb-ai-btn:hover { opacity: 0.9; transform: scale(1.02); }
.tb-ai-btn:active { transform: scale(0.97); }

/* 分隔线 */
.tb-sep {
  width: 1px;
  height: 18px;
  background: rgba(255, 255, 255, 0.12);
  margin: 0 3px;
  flex-shrink: 0;
}

/* 普通按钮 */
.tb-btn {
  min-width: 28px;
  height: 28px;
  padding: 0 6px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: rgba(255, 255, 255, 0.82);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
  display: flex;
  align-items: center;
  justify-content: center;
}
.tb-btn:hover {
  background: rgba(255, 255, 255, 0.12);
  color: #ffffff;
}
.tb-btn:active {
  background: rgba(255, 255, 255, 0.2);
}

/* 格式特殊样式 */
.tb-bold   { font-weight: 700; font-size: 14px; }
.tb-strike { font-size: 14px; }
.tb-italic { font-style: italic; font-size: 14px; }
.tb-under  { font-size: 14px; }
.tb-code   { font-family: 'SF Mono', 'Menlo', monospace; font-size: 11px; letter-spacing: -0.02em; }

/* data-tip tooltip — 出现在按钮上方（因工具栏本身已在选区上方） */
.tb-btn[data-tip],
.tb-ai-btn[data-tip] {
  position: relative;
  overflow: visible;
}

.tb-btn[data-tip]::after,
.tb-ai-btn[data-tip]::after {
  content: attr(data-tip);
  position: absolute;
  bottom: calc(100% + 7px);
  left: 50%;
  transform: translateX(-50%);
  background: rgba(255, 255, 255, 0.96);
  color: #1c1c1e;
  font-size: 11px;
  font-weight: 500;
  padding: 4px 8px;
  border-radius: 5px;
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  transition: opacity 0.15s;
  z-index: 9100;
  letter-spacing: 0;
  line-height: 1.4;
}

.tb-btn[data-tip]:hover::after,
.tb-ai-btn[data-tip]:hover::after {
  opacity: 1;
  transition-delay: 0.35s;
}

/* 小箭头（指向下方选区） */
.tb-arrow {
  position: absolute;
  bottom: -5px;
  left: 50%;
  transform: translateX(-50%);
  width: 10px;
  height: 5px;
  overflow: hidden;
}
.tb-arrow::before {
  content: '';
  position: absolute;
  top: -5px;
  left: 50%;
  transform: translateX(-50%) rotate(45deg);
  width: 10px;
  height: 10px;
  background: #1c1c1e;
  box-shadow: 2px 2px 4px rgba(0, 0, 0, 0.2);
}

/* 显示/隐藏动画 */
.toolbar-pop-enter-active,
.toolbar-pop-leave-active {
  transition: opacity 0.12s ease, transform 0.12s ease;
}
.toolbar-pop-enter-from,
.toolbar-pop-leave-to {
  opacity: 0;
  transform: scale(0.92) translateY(4px);
}
</style>
