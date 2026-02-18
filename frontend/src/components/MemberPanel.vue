<script setup lang="ts">
import { computed } from 'vue'
import { useTeamStore } from '../stores/teamStore'

const store = useTeamStore()
const members = computed(() => store.currentTeam?.members || [])

const steps = [
  { num: '1', text: '输入任务描述' },
  { num: '2', text: 'AI 分析任务，自动生成专家' },
  { num: '3', text: '各专家并行工作' },
  { num: '4', text: '汇总输出最终答案' },
]
</script>

<template>
  <div class="panel-root">
    <div class="panel-header">
      <span class="panel-title">工作流程</span>
    </div>

    <div class="panel-body">
      <!-- 说明卡片 -->
      <div class="info-card">
        <p>专家团队根据每次任务<strong>自动生成</strong>，系统会创建 2-4 个最相关的专家来协作。</p>
      </div>

      <!-- 步骤 -->
      <div class="steps">
        <div v-for="step in steps" :key="step.num" class="step-item">
          <span class="step-num">{{ step.num }}</span>
          <span class="step-text">{{ step.text }}</span>
        </div>
      </div>

      <!-- 常驻成员 -->
      <div v-if="members.length > 0" class="members-section">
        <p class="section-label">常驻成员</p>
        <div v-for="member in members" :key="member.agent_name" class="member-item">
          <div class="member-avatar">TL</div>
          <span class="member-name">{{ member.agent_name }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.panel-root {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-card);
  border-right: 1px solid var(--border);
}

.panel-header {
  padding: 16px 20px 12px;
}

.panel-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 4px 20px 20px;
}

.info-card {
  padding: 14px 16px;
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  margin-bottom: 24px;
}

.info-card p {
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.info-card strong {
  color: var(--accent);
  font-weight: 600;
}

.steps {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.step-item {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}

.step-num {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--accent);
  color: white;
  font-size: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 1px;
}

.step-text {
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.members-section {
  margin-top: 28px;
  padding-top: 20px;
  border-top: 1px solid var(--border);
}

.section-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-light);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 12px;
}

.member-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 0;
}

.member-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--accent);
  color: white;
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.member-name {
  font-size: 13px;
  color: var(--text-secondary);
}
</style>
