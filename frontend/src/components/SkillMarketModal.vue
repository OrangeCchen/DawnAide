<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

const emit = defineEmits<{ close: [] }>()

interface Skill {
  name: string
  display_name: string
  icon: string
  category: string
  description: string
  installed: boolean
}

const searchQuery = ref('')
const activeFilter = ref<'all' | 'installed' | 'available'>('all')

const skills = ref<Skill[]>([])

const builtinSkills: Skill[] = [
  { name: 'time_awareness', display_name: '时间感知', icon: '🕐', category: 'builtin', description: '为所有任务提供当前时间上下文，让专家感知实时时间', installed: true },
  { name: 'file_reading', display_name: '文件读取', icon: '📎', category: 'builtin', description: '读取用户附加的本地文件或目录内容，支持代码、文档等多种格式', installed: true },
  { name: 'web_search', display_name: '联网搜索', icon: '🔍', category: 'tool', description: '通过搜索引擎检索互联网信息，获取最新资料和数据', installed: true },
  { name: 'web_reading', display_name: '网页读取', icon: '📄', category: 'tool', description: '读取和解析指定 URL 的网页内容，提取关键信息', installed: true },
  { name: 'imessage', display_name: 'iMessage', icon: '💬', category: 'tool', description: '通过 Apple iMessage 发送消息给指定联系人', installed: true },
  { name: 'official_document', display_name: '公文写作规范', icon: '📜', category: 'knowledge', description: '基于 GB/T 9704 的中国机关公文写作格式规范和语言要求', installed: true },
]

const marketSkills: Skill[] = [
  { name: 'code_execution', display_name: '代码执行', icon: '⚡', category: 'tool', description: '在沙箱环境中运行 Python / JavaScript 代码，支持数据处理和计算', installed: false },
  { name: 'image_generation', display_name: '图片生成', icon: '🎨', category: 'tool', description: '通过 AI 模型根据文字描述生成高质量图片', installed: false },
  { name: 'video_generation', display_name: '视频生成', icon: '🎬', category: 'tool', description: '基于文本描述或图片生成短视频内容', installed: false },
  { name: 'data_analysis', display_name: '数据分析', icon: '📊', category: 'tool', description: '对 CSV、Excel 等表格数据进行统计分析和可视化', installed: false },
  { name: 'translation', display_name: '多语言翻译', icon: '🌐', category: 'tool', description: '支持中英日韩等多语言互译，保留专业术语和语境', installed: false },
  { name: 'ppt_export', display_name: 'PPT 导出', icon: '📑', category: 'tool', description: '将内容自动排版导出为专业的 PowerPoint 演示文稿', installed: false },
  { name: 'email_send', display_name: '邮件发送', icon: '📧', category: 'tool', description: '通过 SMTP 协议发送邮件，支持附件和 HTML 格式', installed: false },
  { name: 'calendar_sync', display_name: '日程管理', icon: '📅', category: 'tool', description: '创建和管理日历事件，支持 Apple Calendar 同步', installed: false },
  { name: 'mind_map', display_name: '思维导图', icon: '🧠', category: 'tool', description: '根据内容自动生成结构化思维导图并导出为图片', installed: false },
  { name: 'voice_clone', display_name: '语音克隆', icon: '🎙️', category: 'tool', description: '基于少量样本克隆指定音色，生成自然语音播报', installed: false },
]

onMounted(async () => {
  try {
    const res = await fetch('/api/skills')
    if (res.ok) {
      const data = await res.json()
      const serverSkills: string[] = (data.skills || []).map((s: any) => s.name)
      const merged = builtinSkills.map(s => ({
        ...s,
        installed: serverSkills.includes(s.name) || s.installed,
      }))
      skills.value = [...merged, ...marketSkills]
      return
    }
  } catch {
    // API 不可用时使用本地数据
  }
  skills.value = [...builtinSkills, ...marketSkills]
})

const filteredSkills = computed(() => {
  let list = skills.value
  if (activeFilter.value === 'installed') {
    list = list.filter(s => s.installed)
  } else if (activeFilter.value === 'available') {
    list = list.filter(s => !s.installed)
  }
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.trim().toLowerCase()
    list = list.filter(s =>
      s.display_name.toLowerCase().includes(q) ||
      s.description.toLowerCase().includes(q) ||
      s.name.toLowerCase().includes(q)
    )
  }
  return list
})

const installedCount = computed(() => skills.value.filter(s => s.installed).length)
const availableCount = computed(() => skills.value.filter(s => !s.installed).length)

function toggleSkill(skill: Skill) {
  skill.installed = !skill.installed
}

function categoryLabel(cat: string): string {
  const map: Record<string, string> = {
    builtin: '内置',
    tool: '工具',
    knowledge: '知识',
  }
  return map[cat] || cat
}
</script>

<template>
  <div class="market-mask" @click.self="emit('close')">
    <div class="market-card">
      <div class="market-header">
        <div class="market-title-row">
          <h3>技能市场</h3>
          <button class="market-close" @click="emit('close')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <p class="market-subtitle">管理和发现 Agent 技能，为你的智能体团队赋能</p>

        <div class="market-toolbar">
          <div class="market-search">
            <svg class="search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input
              v-model="searchQuery"
              type="text"
              placeholder="搜索技能..."
              class="search-input"
            />
          </div>
          <div class="market-filters">
            <button
              class="filter-btn"
              :class="{ active: activeFilter === 'all' }"
              @click="activeFilter = 'all'"
            >全部</button>
            <button
              class="filter-btn"
              :class="{ active: activeFilter === 'installed' }"
              @click="activeFilter = 'installed'"
            >已安装 ({{ installedCount }})</button>
            <button
              class="filter-btn"
              :class="{ active: activeFilter === 'available' }"
              @click="activeFilter = 'available'"
            >未安装 ({{ availableCount }})</button>
          </div>
        </div>
      </div>

      <div class="market-body">
        <div v-if="filteredSkills.length === 0" class="market-empty">
          没有找到匹配的技能
        </div>
        <div v-else class="skill-grid">
          <div
            v-for="skill in filteredSkills"
            :key="skill.name"
            class="skill-card"
            :class="{ installed: skill.installed }"
          >
            <div class="skill-card-top">
              <span class="skill-icon">{{ skill.icon }}</span>
              <span class="skill-category">{{ categoryLabel(skill.category) }}</span>
            </div>
            <div class="skill-card-body">
              <h4 class="skill-name">{{ skill.display_name }}</h4>
              <p class="skill-desc">{{ skill.description }}</p>
            </div>
            <div class="skill-card-footer">
              <button
                class="skill-action-btn"
                :class="skill.installed ? 'remove' : 'install'"
                @click="toggleSkill(skill)"
              >
                <template v-if="skill.installed">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                  已安装
                </template>
                <template v-else>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                  安装
                </template>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.market-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 30;
  -webkit-app-region: no-drag;
  animation: fadeIn 0.15s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.market-card {
  width: min(720px, 92vw);
  max-height: 80vh;
  border-radius: 14px;
  border: 1px solid var(--border);
  background: var(--bg-secondary);
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.18);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: slideUp 0.2s ease;
}

@keyframes slideUp {
  from { transform: translateY(12px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

.market-header {
  padding: 20px 20px 0;
  flex-shrink: 0;
}

.market-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.market-title-row h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.market-close {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  border: none;
  background: var(--bg-hover);
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.market-close:hover {
  background: var(--border-strong);
  color: var(--text-primary);
}

.market-subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--text-muted);
}

.market-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
}

.market-search {
  position: relative;
  flex: 1;
  max-width: 240px;
}

.search-icon {
  position: absolute;
  left: 8px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-muted);
  pointer-events: none;
}

.search-input {
  width: 100%;
  height: 32px;
  padding: 0 10px 0 28px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s;
}

.search-input::placeholder {
  color: var(--text-muted);
}

.search-input:focus {
  border-color: var(--accent);
}

.market-filters {
  display: flex;
  gap: 4px;
}

.filter-btn {
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-muted);
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.filter-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.filter-btn.active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.market-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px 20px;
}

.market-empty {
  text-align: center;
  padding: 40px 0;
  color: var(--text-muted);
  font-size: 14px;
}

.skill-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.skill-card {
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-primary);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: all 0.2s ease;
}

.skill-card:hover {
  border-color: var(--border-strong);
  box-shadow: var(--shadow-md);
}

.skill-card.installed {
  border-color: rgba(0, 122, 255, 0.15);
  background: rgba(0, 122, 255, 0.02);
}

.skill-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.skill-icon {
  font-size: 24px;
  line-height: 1;
}

.skill-category {
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg-secondary);
  padding: 2px 8px;
  border-radius: 6px;
}

.skill-card-body {
  flex: 1;
}

.skill-name {
  margin: 0 0 4px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.skill-desc {
  margin: 0;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.skill-card-footer {
  display: flex;
  justify-content: flex-end;
}

.skill-action-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 4px 12px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.skill-action-btn.install {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}

.skill-action-btn.install:hover {
  background: #0066d6;
}

.skill-action-btn.remove {
  background: var(--bg-primary);
  color: var(--accent-green);
  border-color: rgba(52, 199, 89, 0.3);
}

.skill-action-btn.remove:hover {
  background: rgba(255, 59, 48, 0.06);
  color: var(--accent-red);
  border-color: rgba(255, 59, 48, 0.3);
}
</style>
