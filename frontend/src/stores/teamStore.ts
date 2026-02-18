import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Team, Message, AgentInfo } from '../types'

export const useTeamStore = defineStore('team', () => {
  // State
  const teams = ref<Team[]>([])
  const currentTeamId = ref<string>('')
  const messages = ref<Record<string, Message[]>>({}) // team_id -> messages
  const agents = ref<AgentInfo[]>([])
  const loading = ref(false)
  const streamTick = ref(0) // 每次流式内容更新时递增，触发滚动

  // Getters
  const currentTeam = computed(() =>
    teams.value.find(t => t.id === currentTeamId.value)
  )
  const currentMessages = computed(() =>
    messages.value[currentTeamId.value] || []
  )

  // Actions
  async function fetchTeams() {
    try {
      const res = await fetch('/api/teams')
      const data = await res.json()
      // 按创建时间倒序（最近创建的在前）
      const sorted = (data.teams as Team[]).sort((a, b) => {
        const ta = a.created_at ? new Date(a.created_at).getTime() : 0
        const tb = b.created_at ? new Date(b.created_at).getTime() : 0
        return tb - ta
      })
      teams.value = sorted
    } catch (e) {
      console.error('Failed to fetch teams:', e)
    }
  }

  async function createTeam(name: string, description: string = '') {
    try {
      loading.value = true
      const res = await fetch('/api/teams', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, description }),
      })
      const team = await res.json()
      // 新团队放到列表最前面
      teams.value.unshift(team)
      currentTeamId.value = team.id
      return team
    } catch (e) {
      console.error('Failed to create team:', e)
    } finally {
      loading.value = false
    }
  }

  async function fetchAgents() {
    try {
      const res = await fetch('/api/agents')
      const data = await res.json()
      agents.value = data.agents
    } catch (e) {
      console.error('Failed to fetch agents:', e)
    }
  }

  async function fetchMessages(teamId: string) {
    try {
      const res = await fetch(`/api/teams/${teamId}/messages`)
      const data = await res.json()
      messages.value[teamId] = data.messages
    } catch (e) {
      console.error('Failed to fetch messages:', e)
    }
  }

  function renameTeam(teamId: string, newName: string) {
    const team = teams.value.find(t => t.id === teamId)
    if (team) {
      team.name = newName
    }
  }

  function addMessage(msg: Message) {
    const teamId = msg.team_id
    if (!teamId) return

    // 处理对话重命名事件
    if (msg.type === 'system' && msg.metadata?.action === 'team_renamed') {
      const newName = msg.metadata.new_name as string
      const targetTeamId = (msg.metadata.team_id as string) || teamId
      if (newName) {
        renameTeam(targetTeamId, newName)
      }
      return
    }

    // 处理流式片段：追加内容到目标消息
    if (msg.type === 'stream_chunk') {
      const targetId = msg.metadata?.target_id
      if (!targetId) return
      const teamMsgs = messages.value[teamId]
      if (!teamMsgs) return
      const target = teamMsgs.find(m => m.id === targetId)
      if (target) {
        if (msg.metadata?.stream_done) {
          // 流式结束：更新状态 + 携带统计数据
          target.metadata = {
            ...target.metadata,
            streaming: false,
            elapsed: msg.metadata.elapsed,
            est_tokens: msg.metadata.est_tokens,
            char_count: msg.metadata.char_count,
          }
          // 支持内容替换（如：任务分析从原始 JSON 替换为结构化文本）
          if (msg.metadata?.replace_content && msg.content) {
            target.content = msg.content
          }
        } else {
          // 追加内容片段
          target.content += msg.content
          streamTick.value++
        }
      }
      return
    }

    if (!messages.value[teamId]) {
      messages.value[teamId] = []
    }
    // 避免重复
    const exists = messages.value[teamId].find(m => m.id === msg.id)
    if (!exists) {
      messages.value[teamId].push(msg)

      // 将有新消息的团队移到列表最前面
      const idx = teams.value.findIndex(t => t.id === teamId)
      if (idx > 0) {
        const [team] = teams.value.splice(idx, 1)
        teams.value.unshift(team)
      }
    }
  }

  async function deleteTeam(teamId: string) {
    try {
      const res = await fetch(`/api/teams/${teamId}`, { method: 'DELETE' })
      if (res.ok) {
        teams.value = teams.value.filter(t => t.id !== teamId)
        delete messages.value[teamId]
        // 如果删的是当前选中的，切到第一个或清空
        if (currentTeamId.value === teamId) {
          currentTeamId.value = teams.value.length > 0 ? teams.value[0].id : ''
          if (currentTeamId.value) fetchMessages(currentTeamId.value)
        }
      }
    } catch (e) {
      console.error('Failed to delete team:', e)
    }
  }

  function selectTeam(teamId: string) {
    currentTeamId.value = teamId
    // 每次切换都拉取最新消息（保证历史记录完整）
    fetchMessages(teamId)
  }

  return {
    teams,
    currentTeamId,
    messages,
    agents,
    loading,
    streamTick,
    currentTeam,
    currentMessages,
    fetchTeams,
    createTeam,
    deleteTeam,
    renameTeam,
    fetchAgents,
    fetchMessages,
    addMessage,
    selectTeam,
  }
})
