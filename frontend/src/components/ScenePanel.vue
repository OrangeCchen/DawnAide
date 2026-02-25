<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

interface SceneField {
  id: string
  label: string
  type: string
  placeholder?: string
  required?: boolean
  options?: string[]
}

interface SceneTemplate {
  id: string
  name: string
  description: string
  fields: SceneField[]
}

interface SceneCategory {
  name: string
  display_name: string
  icon: string
  description: string
  methodology: string
  children: SceneTemplate[]
}

const emit = defineEmits<{
  (e: 'submit', payload: {
    description: string
    title: string
    sceneType: string
    sceneCategory: string
    sceneFormData: Record<string, string>
  }): void
  (e: 'context-change', payload: {
    sceneCategory: string
    sceneType: string
  }): void
}>()

const scenes = ref<SceneCategory[]>([])
const loading = ref(true)
const selectedCategory = ref<SceneCategory | null>(null)
const selectedTemplate = ref<SceneTemplate | null>(null)
const formData = ref<Record<string, string>>({})

onMounted(async () => {
  try {
    const res = await fetch('/api/scenes')
    if (res.ok) {
      const data = await res.json()
      scenes.value = data.scenes || []
    }
  } catch (e) {
    console.error('Failed to load scenes:', e)
  } finally {
    loading.value = false
  }
})

function selectCategory(cat: SceneCategory) {
  selectedCategory.value = cat
  selectedTemplate.value = null
  formData.value = {}
  emit('context-change', { sceneCategory: cat.name, sceneType: '' })
}

function selectTemplate(tmpl: SceneTemplate) {
  selectedTemplate.value = tmpl
  const data: Record<string, string> = {}
  for (const f of tmpl.fields) {
    data[f.id] = ''
  }
  formData.value = data
  emit('context-change', {
    sceneCategory: selectedCategory.value?.name || '',
    sceneType: tmpl.id,
  })
}

function goBack() {
  if (selectedTemplate.value) {
    selectedTemplate.value = null
    formData.value = {}
    emit('context-change', {
      sceneCategory: selectedCategory.value?.name || '',
      sceneType: '',
    })
  } else if (selectedCategory.value) {
    selectedCategory.value = null
    emit('context-change', { sceneCategory: '', sceneType: '' })
  }
}

function onFieldInput(fieldId: string, value: string) {
  formData.value = { ...formData.value, [fieldId]: value }
}

function onSelectField(fieldId: string, option: string) {
  formData.value = { ...formData.value, [fieldId]: option }
}

function onTextInput(fieldId: string, event: Event) {
  const target = event.target as HTMLInputElement | null
  onFieldInput(fieldId, target?.value ?? '')
}

const requiredFields = computed(() => {
  if (!selectedTemplate.value) return []
  return selectedTemplate.value.fields.filter(field => field.required)
})

const optionalFields = computed(() => {
  if (!selectedTemplate.value) return []
  return selectedTemplate.value.fields.filter(field => !field.required)
})

const requiredCompletedCount = computed(() => {
  return requiredFields.value.reduce((count, field) => {
    const val = formData.value[field.id]
    return val && val.trim() ? count + 1 : count
  }, 0)
})

const missingRequiredLabels = computed(() => {
  return requiredFields.value
    .filter(field => {
      const val = formData.value[field.id]
      return !val || !val.trim()
    })
    .map(field => field.label)
})

const canGenerate = computed(() => {
  if (!selectedTemplate.value || !selectedCategory.value) return false
  return missingRequiredLabels.value.length === 0
})

const fileOrganizeScene: SceneCategory = {
  name: 'file_organize',
  display_name: '文件整理',
  icon: '🗂️',
  description: '智能整理和管理本地文件',
  methodology: '',
  children: [
    {
      id: 'file_organize_plan',
      name: '整理方案生成',
      description: '根据你的目录结构和目标，生成可执行整理方案',
      fields: [
        { id: 'folder_scope', label: '待整理目录', type: 'text', placeholder: '例如：~/Documents/项目资料', required: true },
        { id: 'organize_goal', label: '整理目标', type: 'text', placeholder: '可选；不填则先由系统分析并给出建议', required: false },
      ],
    },
  ],
}

const displayScenes = computed(() => {
  const hasFileOrganize = scenes.value.some(
    scene => scene.name === fileOrganizeScene.name || scene.display_name === fileOrganizeScene.display_name
  )
  if (hasFileOrganize) return scenes.value
  return [fileOrganizeScene, ...scenes.value]
})

function isFieldFilled(fieldId: string) {
  const val = formData.value[fieldId]
  return Boolean(val && val.trim())
}

function handleSubmit() {
  if (!canGenerate.value || !selectedTemplate.value || !selectedCategory.value) return

  // 拼接 prompt
  const parts: string[] = []
  const sceneFormData: Record<string, string> = {}
  for (const field of selectedTemplate.value.fields) {
    const val = formData.value[field.id]
    if (val && val.trim()) {
      const cleanVal = val.trim()
      parts.push(`${field.label}：${cleanVal}`)
      sceneFormData[field.id] = cleanVal
    }
  }
  const description = `【${selectedCategory.value.display_name} · ${selectedTemplate.value.name}】\n\n${parts.join('\n')}`

  emit('submit', {
    description,
    title: `${selectedTemplate.value.name}`,
    sceneType: selectedTemplate.value.id,
    sceneCategory: selectedCategory.value.name,
    sceneFormData,
  })
}
</script>

<template>
  <div class="scene-panel">
    <!-- 层级 1：场景分类卡片 -->
    <template v-if="!selectedCategory">
      <div class="scene-header">
        <div class="scene-logo">
          <svg width="48" height="48" viewBox="0 0 72 62" fill="none">
            <defs>
              <linearGradient id="sg1" x1="0" y1="0" x2="72" y2="62" gradientUnits="userSpaceOnUse">
                <stop stop-color="#007AFF"/>
                <stop offset="1" stop-color="#AF52DE"/>
              </linearGradient>
            </defs>
            <circle cx="36" cy="20" r="10" fill="url(#sg1)" opacity="0.8"/>
            <circle cx="18" cy="45" r="8" fill="url(#sg1)" opacity="0.6"/>
            <circle cx="54" cy="45" r="8" fill="url(#sg1)" opacity="0.6"/>
            <circle cx="36" cy="56" r="6" fill="url(#sg1)" opacity="0.9"/>
          </svg>
        </div>
        <h3 class="scene-title">选择使用场景</h3>
        <p class="scene-desc">选择一个场景模板，系统会引导你填写关键信息，确保输出质量。</p>
      </div>
      <div class="scene-grid" v-if="!loading">
        <button
          v-for="cat in displayScenes"
          :key="cat.name"
          class="scene-card"
          @click="selectCategory(cat)"
        >
          <span class="scene-card-icon-wrap">
            <span class="scene-card-icon">{{ cat.icon }}</span>
          </span>
          <span class="scene-card-name">{{ cat.display_name }}</span>
          <span class="scene-card-desc">{{ cat.description }}</span>
        </button>
      </div>
      <p class="scene-hint">或直接在下方输入框描述你的任务</p>
    </template>

    <!-- 层级 2：子类型选择 -->
    <template v-else-if="!selectedTemplate">
      <div class="scene-sub-header">
        <button class="back-btn" @click="goBack">← 返回</button>
        <h3 class="scene-sub-title">
          {{ selectedCategory.icon }} {{ selectedCategory.display_name }}
        </h3>
        <p class="scene-sub-desc">请选择具体类型</p>
      </div>
      <div class="template-grid">
        <button
          v-for="tmpl in selectedCategory.children"
          :key="tmpl.id"
          class="template-card"
          @click="selectTemplate(tmpl)"
        >
          <span class="template-name">{{ tmpl.name }}</span>
          <span class="template-desc">{{ tmpl.description }}</span>
        </button>
      </div>
    </template>

    <!-- 层级 3：信息填写表单 -->
    <template v-else>
      <div class="scene-sub-header">
        <button class="back-btn" @click="goBack">← 返回</button>
        <h3 class="scene-sub-title">
          {{ selectedCategory?.icon }} {{ selectedTemplate.name }}
        </h3>
        <p class="scene-sub-desc">请填写以下信息，系统将据此生成专业内容</p>
      </div>
      <div class="scene-form">
        <div class="interaction-card">
          <div class="interaction-card-header">
            <h4 class="interaction-title">交互模块（必填）</h4>
            <span class="interaction-progress">{{ requiredCompletedCount }}/{{ requiredFields.length }}</span>
          </div>
          <p class="interaction-desc">完成以下必填项后，即可直接生成内容。</p>
          <div v-for="field in requiredFields" :key="field.id" class="form-field">
            <label class="form-label">
              {{ field.label }}
              <span class="form-required">*</span>
            </label>

            <input
              v-if="field.type === 'text'"
              type="text"
              :placeholder="field.placeholder || '请输入...'"
              :value="formData[field.id] || ''"
              @input="onTextInput(field.id, $event)"
              class="form-input"
              :class="{ filled: isFieldFilled(field.id) }"
            />

            <div v-else-if="field.type === 'select'" class="form-options">
              <button
                v-for="opt in field.options"
                :key="opt"
                @click="onSelectField(field.id, opt)"
                class="form-option-btn"
                :class="{ selected: formData[field.id] === opt }"
              >{{ opt }}</button>
            </div>
          </div>

          <p v-if="missingRequiredLabels.length" class="form-missing">
            待补全：{{ missingRequiredLabels.join('、') }}
          </p>
          <p v-else class="form-ready-tip">必填项已完成，可直接生成。</p>
        </div>

        <div v-if="optionalFields.length" class="interaction-card optional-card">
          <div class="interaction-card-header">
            <h4 class="interaction-title">补充信息（可选）</h4>
            <span class="interaction-progress">选填</span>
          </div>
          <p class="interaction-desc">补充越完整，生成结果越贴近你的真实场景。</p>
          <div v-for="field in optionalFields" :key="field.id" class="form-field">
            <label class="form-label">{{ field.label }}</label>

            <input
              v-if="field.type === 'text'"
              type="text"
              :placeholder="field.placeholder || '请输入...'"
              :value="formData[field.id] || ''"
              @input="onTextInput(field.id, $event)"
              class="form-input"
            />

            <div v-else-if="field.type === 'select'" class="form-options">
              <button
                v-for="opt in field.options"
                :key="opt"
                @click="onSelectField(field.id, opt)"
                class="form-option-btn"
                :class="{ selected: formData[field.id] === opt }"
              >{{ opt }}</button>
            </div>
          </div>
        </div>

        <button
          class="form-submit-btn"
          :class="{ ready: canGenerate }"
          :disabled="!canGenerate"
          @click="handleSubmit"
        >
          生成内容
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.scene-panel {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: 18px 20px 16px;
  width: 100%;
  max-width: 920px;
  margin: 0 auto;
  box-sizing: border-box;
  background: #f8f8f8;
  border-radius: 18px;
}

.scene-header {
  text-align: left;
  margin-bottom: 16px;
}

.scene-logo {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  background: #effaf4;
  margin-bottom: 10px;
}

.scene-title {
  font-size: clamp(22px, 2vw, 30px);
  font-weight: 700;
  line-height: 1.2;
  color: #171717;
  margin-bottom: 6px;
}

.scene-desc {
  font-size: clamp(12px, 1.2vw, 16px);
  color: #7a7a7a;
  line-height: 1.45;
}

.scene-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  width: 100%;
  margin-bottom: 10px;
}

.scene-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: 14px 14px 12px;
  min-width: 0;
  border: 1px solid #e6e6e6;
  border-radius: 12px;
  background: #f7f7f7;
  cursor: pointer;
  transition: all 0.2s ease;
  text-align: left;
}

.scene-card:hover {
  border-color: #cfd5d1;
  background: #f4f4f4;
  transform: translateY(-1px);
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.05);
}

.scene-card-icon-wrap {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  border: 1px solid #e6e6e6;
  background: #eef8f2;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 10px;
}

.scene-card-icon {
  font-size: 18px;
  line-height: 1;
}

.scene-card-name {
  font-size: clamp(15px, 1.4vw, 20px);
  font-weight: 700;
  color: #171717;
  margin-bottom: 6px;
  line-height: 1.25;
}

.scene-card-desc {
  font-size: clamp(11px, 1.1vw, 14px);
  color: #777777;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.scene-hint {
  font-size: clamp(11px, 1vw, 13px);
  color: #999999;
}

@media (max-width: 1024px) {
  .scene-panel {
    padding: 14px 14px 14px;
    border-radius: 16px;
  }

  .scene-title {
    font-size: 22px;
  }

  .scene-desc {
    font-size: 13px;
  }

  .scene-card-name {
    font-size: 16px;
  }

  .scene-card-desc {
    font-size: 12px;
  }

  .scene-hint {
    font-size: 12px;
  }
}

/* 子类型选择 */
.scene-sub-header {
  width: 100%;
  margin-bottom: 20px;
}

.back-btn {
  display: inline-flex;
  align-items: center;
  font-size: 13px;
  color: var(--accent);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  margin-bottom: 12px;
}

.back-btn:hover {
  opacity: 0.7;
}

.scene-sub-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.scene-sub-desc {
  font-size: 13px;
  color: var(--text-muted);
}

.template-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 10px;
  width: 100%;
}

.template-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: 14px;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-card);
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
}

.template-card:hover {
  border-color: var(--accent);
  background: var(--bg-active);
}

.template-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 2px;
}

.template-desc {
  font-size: 12px;
  color: var(--text-muted);
}

/* 表单 */
.scene-form {
  width: 100%;
}

.interaction-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-card);
  padding: 14px;
  margin-bottom: 12px;
}

.interaction-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.interaction-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.interaction-progress {
  font-size: 12px;
  color: var(--accent);
  background: var(--bg-active);
  border-radius: 999px;
  padding: 2px 8px;
}

.interaction-desc {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 10px;
}

.optional-card .interaction-progress {
  color: var(--text-muted);
}

.form-field {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.form-required {
  color: var(--accent-red);
  margin-left: 2px;
}

.form-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-card);
  color: var(--text-primary);
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
  box-sizing: border-box;
}

.form-input:focus {
  border-color: var(--accent);
}

.form-input::placeholder {
  color: var(--text-light);
}

.form-input.filled {
  border-color: var(--accent);
}

.form-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.form-option-btn {
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: 20px;
  background: var(--bg-card);
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.form-option-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.form-option-btn.selected {
  background: var(--accent);
  color: white;
  border-color: var(--accent);
}

.form-missing {
  font-size: 12px;
  color: var(--accent-red);
}

.form-ready-tip {
  font-size: 12px;
  color: var(--accent);
}

.form-submit-btn {
  width: 100%;
  margin-top: 20px;
  padding: 10px 24px;
  border-radius: var(--radius-md);
  border: none;
  background: var(--bg-tertiary);
  color: var(--text-light);
  font-size: 15px;
  font-weight: 500;
  cursor: not-allowed;
  transition: all 0.2s;
}

.form-submit-btn.ready {
  background: var(--accent);
  color: white;
  cursor: pointer;
}

.form-submit-btn.ready:hover {
  opacity: 0.85;
}
</style>
