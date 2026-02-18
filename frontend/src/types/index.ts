export interface TeamMember {
  agent_name: string
  role: string
  role_label: string
  status: string
}

export interface Team {
  id: string
  name: string
  description: string
  members: TeamMember[]
  member_count: number
  created_at: string
  metadata: Record<string, any>
}

export interface Message {
  id: string
  type: 'task_assignment' | 'task_result' | 'agent_message' | 'status_update' | 'system' | 'stream_chunk'
  sender: string
  receiver: string
  team_id: string
  content: string
  metadata: Record<string, any>
  timestamp: string
  formatted_content?: string
  status_badge?: string
}

export interface AgentInfo {
  name: string
  role: string
  role_label: string
  status: string
}
