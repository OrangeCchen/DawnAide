/**
 * 知识库 API 调用层
 */

const API_BASE = '' // 同源请求

// Types
export interface Source {
  id: string
  name: string
  type: string
  size: number
  chunk_count: number
  created_at: string
}

export interface SourceListResponse {
  sources: Source[]
  total_chunks: number
}

export interface SearchResult {
  id: string
  score: number
  content: string
  source_name: string
  source_id: string
}

export interface SearchResponse {
  query: string
  results: SearchResult[]
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface Citation {
  source_id: string
  source_name: string
  chunk: string
}

export interface ChatResponse {
  answer: string
  citations: Citation[]
}

export interface KbStats {
  total_sources: number
  total_chunks: number
  collection_name: string
}

// API Functions

/**
 * 获取知识库来源列表
 */
export async function getSources(): Promise<SourceListResponse> {
  const res = await fetch(`${API_BASE}/api/kb/sources`, {
    credentials: 'include',
  })
  if (!res.ok) {
    throw new Error(`获取来源失败: ${res.status}`)
  }
  return res.json()
}

/**
 * 上传文件到知识库
 */
export async function uploadSource(file: File): Promise<{ success: boolean; source: Source }> {
  const formData = new FormData()
  formData.append('file', file)

  const res = await fetch(`${API_BASE}/api/kb/sources/upload`, {
    method: 'POST',
    body: formData,
    credentials: 'include',
  })

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: '上传失败' }))
    throw new Error(error.detail || `上传失败: ${res.status}`)
  }
  return res.json()
}

/**
 * 添加网页链接到知识库
 */
export async function addLink(url: string): Promise<{ success: boolean; source: Source }> {
  const formData = new FormData()
  formData.append('url', url)

  const res = await fetch(`${API_BASE}/api/kb/sources/link`, {
    method: 'POST',
    body: formData,
    credentials: 'include',
  })

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: '添加链接失败' }))
    throw new Error(error.detail || `添加链接失败: ${res.status}`)
  }
  return res.json()
}

/**
 * 添加纯文本到知识库
 */
export async function addTextSource(name: string, content: string): Promise<{ success: boolean; source: Source }> {
  const formData = new FormData()
  formData.append('name', name)
  formData.append('content', content)

  const res = await fetch(`${API_BASE}/api/kb/sources/text`, {
    method: 'POST',
    body: formData,
    credentials: 'include',
  })

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: '添加文本失败' }))
    throw new Error(error.detail || `添加文本失败: ${res.status}`)
  }
  return res.json()
}

/**
 * 删除知识来源
 */
export async function deleteSource(sourceId: string): Promise<{ success: boolean }> {
  const res = await fetch(`${API_BASE}/api/kb/sources/${sourceId}`, {
    method: 'DELETE',
    credentials: 'include',
  })

  if (!res.ok) {
    throw new Error(`删除失败: ${res.status}`)
  }
  return res.json()
}

/**
 * 语义检索知识库
 */
export async function searchKnowledge(query: string, limit: number = 5): Promise<SearchResponse> {
  const res = await fetch(`${API_BASE}/api/kb/search`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query, limit }),
    credentials: 'include',
  })

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: '检索失败' }))
    throw new Error(error.detail || `检索失败: ${res.status}`)
  }
  return res.json()
}

/**
 * 基于知识库对话
 */
export async function chatWithKnowledge(
  message: string,
  history: ChatMessage[] = []
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/api/kb/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ message, history }),
    credentials: 'include',
  })

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: '对话失败' }))
    throw new Error(error.detail || `对话失败: ${res.status}`)
  }
  return res.json()
}

/**
 * 获取知识库统计信息
 */
export async function getKbStats(): Promise<KbStats> {
  const res = await fetch(`${API_BASE}/api/kb/stats`, {
    credentials: 'include',
  })

  if (!res.ok) {
    throw new Error(`获取统计失败: ${res.status}`)
  }
  return res.json()
}
