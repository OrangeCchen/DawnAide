<script setup lang="ts">
import { computed } from 'vue'

const emit = defineEmits<{
  close: []
}>()

const currentTimeText = computed(() => new Date().toLocaleString())
</script>

<template>
  <div class="memory-mask" @click.self="emit('close')">
    <div class="memory-card">
      <div class="memory-card-header">
        <h3>记忆</h3>
        <button class="memory-close" @click="emit('close')">关闭</button>
      </div>
      <p class="memory-desc">记忆模块初稿界面，用于展示会话上下文和关键偏好。</p>
      <div class="memory-section">
        <h4>会话记忆</h4>
        <p>当前会话中可被复用的关键信息（如目标、约束、已确认事实）。</p>
      </div>
      <div class="memory-section">
        <h4>长期偏好</h4>
        <p>例如写作风格、输出格式、常用术语等，后续可手动编辑。</p>
      </div>
      <div class="memory-section">
        <h4>更新时间</h4>
        <p>{{ currentTimeText }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.memory-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 30;
  -webkit-app-region: no-drag;
}

.memory-card {
  width: min(560px, 92vw);
  border-radius: 14px;
  border: 1px solid var(--border);
  background: var(--bg-secondary);
  padding: 16px;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.2);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.memory-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.memory-card-header h3 {
  margin: 0;
  font-size: 18px;
  color: var(--text-primary);
}

.memory-close {
  border: 1px solid var(--border);
  background: var(--bg-primary);
  color: var(--text-secondary);
  border-radius: 8px;
  padding: 4px 10px;
  cursor: pointer;
}

.memory-desc {
  margin: 0;
  color: var(--text-secondary);
}

.memory-section {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-primary);
  padding: 12px;
}

.memory-section h4 {
  margin: 0 0 6px;
  color: var(--text-primary);
  font-size: 14px;
}

.memory-section p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.5;
}
</style>
