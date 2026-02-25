<script setup lang="ts">
import { ref, watch, computed } from 'vue'

interface MonitorItem {
  id: string
  title?: string
  name?: string
  status?: string
  detail?: string
  path?: string
  openable?: boolean
}

interface MonitorPayload {
  task_type?: string
  note?: string
  workspace?: string
  todo?: MonitorItem[]
  artifacts?: MonitorItem[]
  skills?: MonitorItem[]
  pending_confirm?: boolean
  preview_plan?: {
    root_dir: string
    total_files: number
    category_counts: Record<string, number>
    sample_moves: Array<{ source: string; target: string }>
  }
  organize_goal?: string
  goal_suggestions?: Array<{
    id: string
    title: string
    goal: string
    reason: string
  }>
}

const props = defineProps<{
  monitor: MonitorPayload
}>()

const emit = defineEmits<{
  confirmExecute: [workspace: string, organizeGoal: string]
  reAnalyze: [workspace: string, newGoal: string]
}>()

const todoOpen = ref(true)
const artifactsOpen = ref(true)
const skillsOpen = ref(false)
const panelCollapsed = ref(false)
const openingPath = ref('')
const confirming = ref(false)
// 用 suggestion id 追踪已选项，避免 goal 文本重复导致多选高亮
const selectedId = ref('')
// 标记用户是否主动选了与当前分析不同的目标
const userPickedSuggestion = ref(false)

// 当前选中的 goal 文本（由 selectedId 推导）
const selectedGoal = computed(() =>
  props.monitor.goal_suggestions?.find(s => s.id === selectedId.value)?.goal || ''
)

watch(
  () => props.monitor,
  (monitor) => {
    if (!monitor) return
    // monitor 更新（新一轮分析）时重置用户选择状态
    userPickedSuggestion.value = false
    // 找到与当前 organize_goal 匹配的建议 id，默认选中它
    const currentGoal = (monitor.organize_goal || '').trim()
    const matched = monitor.goal_suggestions?.find(
      s => s.goal === currentGoal
    )
    if (matched) {
      selectedId.value = matched.id
    } else {
      // 无匹配时默认选第一个
      selectedId.value = monitor.goal_suggestions?.[0]?.id || ''
    }
  },
  { immediate: true, deep: true }
)

function pickSuggestion(id: string, goal: string) {
  selectedId.value = id
  const current = (props.monitor.organize_goal || '').trim()
  userPickedSuggestion.value = goal.trim() !== current
}

// 只有用户主动选了与当前分析结果不同的目标才进入重新分析模式
const isReAnalyze = computed(() => userPickedSuggestion.value)

function statusIcon(status?: string) {
  if (status === 'done') return '✅'
  if (status === 'running') return '⏳'
  if (status === 'failed') return '❌'
  return '○'
}

async function openLocalPath(path?: string) {
  if (!path || openingPath.value) return
  openingPath.value = path
  try {
    const res = await fetch('/api/local/open-path', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    })
    if (!res.ok) {
      const data = await res.json().catch(() => null)
      globalThis.alert(data?.detail || '打开目录失败')
    }
  } catch (_e) {
    globalThis.alert('打开目录失败，请确认桌面 Runtime 已启动。')
  } finally {
    openingPath.value = ''
  }
}

function handleConfirmExecute() {
  if (confirming.value || !props.monitor.workspace) return
  confirming.value = true
  const goal = selectedGoal.value || props.monitor.organize_goal || ''
  if (isReAnalyze.value) {
    emit('reAnalyze', props.monitor.workspace, goal)
  } else {
    emit('confirmExecute', props.monitor.workspace, goal)
  }
  setTimeout(() => { confirming.value = false }, 2000)
}

const confirmButtonText = computed(() => {
  if (isReAnalyze.value) return confirming.value ? '分析中...' : '重新分析并预览'
  return confirming.value ? '执行中...' : '确认执行'
})
</script>

<template>
  <!-- 外层 wrapper：tab 按钮 + 面板并排 -->
  <div class="monitor-wrapper">
    <!-- 侧边折叠 Tab（始终可见） -->
    <button
      class="panel-tab"
      :title="panelCollapsed ? '展开任务监控' : '收起任务监控'"
      @click="panelCollapsed = !panelCollapsed"
    >
      <span class="tab-arrow">{{ panelCollapsed ? '〈' : '〉' }}</span>
    </button>

    <!-- 面板主体 -->
    <aside v-if="!panelCollapsed" class="monitor-card">
      <!-- 固定头部 -->
      <div class="monitor-head">
        <h3 class="monitor-title">任务监控</h3>
      </div>

      <!-- 可滚动内容区 -->
      <div class="monitor-body">
        <div v-if="monitor.note" class="monitor-note">{{ monitor.note }}</div>

        <!-- 整理目标建议（单选） -->
        <section v-if="monitor.goal_suggestions?.length" class="monitor-section">
          <div class="section-label">整理目标建议</div>
          <div class="goal-list">
            <button
              v-for="item in monitor.goal_suggestions"
              :key="item.id"
              class="goal-btn"
              :class="{ selected: selectedId === item.id }"
              @click="pickSuggestion(item.id, item.goal)"
            >
              <span class="goal-radio">
                <span class="goal-radio-dot" />
              </span>
              <span class="goal-text">
                <span class="goal-title">{{ item.title }}</span>
                <span class="goal-reason">{{ item.reason }}</span>
              </span>
            </button>
          </div>
        </section>

        <!-- 待办 -->
        <section class="monitor-section">
          <button class="section-head" @click="todoOpen = !todoOpen">
            <span>待办</span>
            <span class="arrow" :class="{ open: todoOpen }">⌄</span>
          </button>
          <div v-if="todoOpen" class="section-body">
            <div v-for="item in monitor.todo || []" :key="item.id" class="todo-item">
              <span class="todo-icon">{{ statusIcon(item.status) }}</span>
              <div class="todo-content">
                <div class="todo-text">{{ item.title || item.name }}</div>
                <div v-if="item.detail" class="todo-detail">{{ item.detail }}</div>
              </div>
            </div>
          </div>
        </section>

        <!-- 产物 -->
        <section class="monitor-section">
          <button class="section-head" @click="artifactsOpen = !artifactsOpen">
            <span>产物</span>
            <span class="arrow" :class="{ open: artifactsOpen }">⌄</span>
          </button>
          <div v-if="artifactsOpen" class="section-body">
            <div v-if="!monitor.artifacts || monitor.artifacts.length === 0" class="empty-line">暂无产物</div>
            <div v-for="item in monitor.artifacts || []" :key="item.id" class="artifact-item">
              <div class="artifact-head">
                <div class="artifact-name">{{ item.name }}</div>
                <button
                  v-if="item.openable && item.path"
                  class="open-btn"
                  :disabled="openingPath === item.path"
                  @click="openLocalPath(item.path)"
                >{{ openingPath === item.path ? '打开中...' : '打开' }}</button>
              </div>
              <div class="artifact-path" :title="item.path">{{ item.path }}</div>
            </div>
          </div>
        </section>

        <!-- 技能 -->
        <section class="monitor-section">
          <button class="section-head" @click="skillsOpen = !skillsOpen">
            <span>技能</span>
            <span class="arrow" :class="{ open: skillsOpen }">⌄</span>
          </button>
          <div v-if="skillsOpen" class="section-body">
            <div v-if="!monitor.skills || monitor.skills.length === 0" class="empty-line">没有技能</div>
            <div v-for="item in monitor.skills || []" :key="item.id || item.name" class="skill-item">
              {{ item.name || item.title }}
            </div>
          </div>
        </section>
      </div>

      <!-- 固定底部：确认执行按钮 -->
      <div v-if="monitor.pending_confirm" class="monitor-footer">
        <button
          class="confirm-btn"
          :class="{ reanalyze: isReAnalyze }"
          :disabled="confirming"
          @click="handleConfirmExecute"
        >
          {{ confirmButtonText }}
        </button>
      </div>
    </aside>
  </div>
</template>

<style scoped>
/* ===== 外层 wrapper ===== */
.monitor-wrapper {
  display: flex;
  align-items: center;
  gap: 0;
}

/* ===== 侧边 Tab ===== */
.panel-tab {
  width: 22px;
  height: 56px;
  background: #fff;
  border: 1px solid #dfdfdf;
  border-right: none;
  border-radius: 8px 0 0 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: -3px 0 8px rgba(0, 0, 0, 0.04);
  flex-shrink: 0;
  padding: 0;
  transition: background 0.15s;
}

.panel-tab:hover {
  background: #f5f5f5;
}

.tab-arrow {
  font-size: 11px;
  color: #888;
  line-height: 1;
}

/* ===== 面板主体 ===== */
.monitor-card {
  width: 260px;
  /* 约为视口高度的 45% */
  max-height: 45vh;
  border: 1px solid #dfdfdf;
  border-radius: 0 12px 12px 0;
  background: rgba(255, 255, 255, 0.97);
  backdrop-filter: blur(4px);
  box-shadow: 4px 0 20px rgba(0, 0, 0, 0.07);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ===== 固定头部 ===== */
.monitor-head {
  flex-shrink: 0;
  padding: 10px 12px 8px;
  border-bottom: 1px solid #f0f0f0;
}

.monitor-title {
  font-size: 14px;
  font-weight: 700;
  color: #212121;
  margin: 0;
  letter-spacing: 0.01em;
}

/* ===== 可滚动内容 ===== */
.monitor-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px 12px 4px;
}

.monitor-note {
  font-size: 11px;
  color: #6f6f6f;
  line-height: 1.4;
  margin-bottom: 6px;
}

/* ===== 固定底部 ===== */
.monitor-footer {
  flex-shrink: 0;
  padding: 8px 12px 10px;
  border-top: 1px solid #f0f0f0;
}

/* ===== 分区 ===== */
.monitor-section {
  border-top: 1px dashed #ebebeb;
  padding-top: 8px;
  margin-top: 6px;
}

.monitor-section:first-child {
  border-top: none;
  margin-top: 0;
}

.section-head {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 0;
  background: transparent;
  padding: 0;
  font-size: 13px;
  color: #333;
  font-weight: 600;
  cursor: pointer;
}

.section-label {
  font-size: 13px;
  color: #333;
  font-weight: 600;
  margin-bottom: 6px;
}

.arrow {
  display: inline-block;
  color: #aaa;
  font-size: 12px;
  transition: transform 0.2s ease;
}

.arrow.open {
  transform: rotate(180deg);
}

.section-body {
  margin-top: 6px;
}

/* ===== 整理目标建议（单选） ===== */
.goal-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.goal-btn {
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: 7px;
  text-align: left;
  border: 1px solid #e8e8e8;
  background: #fafafa;
  border-radius: 8px;
  padding: 7px 9px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.goal-btn:hover {
  border-color: #c8c8c8;
  background: #f5f5f5;
}

.goal-btn.selected {
  border-color: #4CAF50;
  background: rgba(76, 175, 80, 0.06);
}

/* 单选圆圈 */
.goal-radio {
  flex-shrink: 0;
  width: 14px;
  height: 14px;
  border: 1.5px solid #d0d0d0;
  border-radius: 50%;
  margin-top: 2px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: border-color 0.15s;
}

.goal-btn.selected .goal-radio {
  border-color: #4CAF50;
}

.goal-radio-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: transparent;
  transition: background 0.15s;
}

.goal-btn.selected .goal-radio-dot {
  background: #4CAF50;
}

.goal-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.goal-title {
  font-size: 12px;
  color: #2e2e2e;
  font-weight: 600;
  line-height: 1.3;
}

.goal-reason {
  font-size: 11px;
  color: #888;
  line-height: 1.3;
}

/* ===== 待办 ===== */
.todo-item {
  display: flex;
  align-items: flex-start;
  gap: 5px;
  margin-bottom: 5px;
}

.todo-icon {
  width: 14px;
  flex-shrink: 0;
  font-size: 12px;
  line-height: 1.6;
}

.todo-content {
  min-width: 0;
}

.todo-text {
  font-size: 12px;
  color: #4a4a4a;
  line-height: 1.45;
}

.todo-detail {
  font-size: 11px;
  color: #9a9a9a;
  line-height: 1.3;
  margin-top: 1px;
}

/* ===== 产物 ===== */
.artifact-item {
  margin-bottom: 6px;
}

.artifact-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.artifact-name {
  font-size: 12px;
  color: #2e2e2e;
  font-weight: 500;
}

.artifact-path {
  font-size: 11px;
  color: #888;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.open-btn {
  border: 1px solid #d8d8d8;
  background: #fff;
  border-radius: 6px;
  font-size: 11px;
  color: #555;
  padding: 1px 7px;
  cursor: pointer;
  flex-shrink: 0;
}

.open-btn:hover:not(:disabled) {
  border-color: #bdbdbd;
  color: #222;
}

.open-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

/* ===== 技能 / 空状态 ===== */
.skill-item,
.empty-line {
  font-size: 12px;
  color: #999;
}

/* ===== 确认执行按钮 ===== */
.confirm-btn {
  width: 100%;
  padding: 9px 14px;
  background: #4CAF50;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.confirm-btn:hover:not(:disabled) {
  background: #43a047;
}

.confirm-btn.reanalyze {
  background: #1976d2;
}

.confirm-btn.reanalyze:hover:not(:disabled) {
  background: #1565c0;
}

.confirm-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
