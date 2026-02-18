<template>
  <div class="notebooklm-panel">
    <!-- 顶部标题栏 -->
    <div class="panel-header">
      <div class="header-left">
        <div class="logo-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M4 4h16v16H4V4z" stroke="currentColor" stroke-width="2"/>
            <path d="M8 8h8M8 12h8M8 16h5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
        </div>
        <h2>知识库</h2>
        <span class="source-count">{{ sources.length }} 个来源 · {{ totalChunks }} 个片段</span>
      </div>
      <div class="header-actions">
        <button class="action-btn primary" @click="openStudio">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path d="M12 3v18M3 12h18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          创建输出
        </button>
      </div>
    </div>

    <!-- 三面板布局 -->
    <div class="panels-container">
      <!-- 来源面板 -->
      <div class="source-panel">
        <div class="panel-section">
          <div class="section-header">
            <h3>来源</h3>
            <button class="add-btn" @click="addSource">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                <path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
              </svg>
              添加
            </button>
          </div>
          
          <!-- 拖拽上传区 -->
          <div 
            class="drop-zone"
            :class="{ 'drag-over': isDragOver, 'uploading': isUploading }"
            @dragover.prevent="isDragOver = true"
            @dragleave="isDragOver = false"
            @drop.prevent="handleDrop"
          >
            <svg v-if="!isUploading" width="32" height="32" viewBox="0 0 24 24" fill="none">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="currentColor" stroke-width="1.5"/>
              <path d="M14 2v6h6M12 18v-6M9 15l3-3 3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <svg v-else width="32" height="32" viewBox="0 0 24 24" fill="none" class="spinner">
              <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" stroke-dasharray="32" stroke-linecap="round"/>
            </svg>
            <p v-if="!isUploading">拖拽文件到此处</p>
            <p v-else>正在上传和处理...</p>
            <span>支持 TXT、MD、PDF、Word</span>
          </div>

          <!-- 来源列表 -->
          <div class="source-list">
            <!-- 加载中 -->
            <div v-if="isLoading" class="loading-state">
              <p>加载中...</p>
            </div>
            
            <!-- 空状态 -->
            <div v-else-if="sources.length === 0" class="empty-source-state">
              <p>暂无知识来源</p>
              <span>上传文档或添加链接开始构建知识库</span>
            </div>
            <div 
              v-for="source in sources" 
              :key="source.id"
              class="source-item"
              :class="{ active: activeSource === source.id }"
              @click="selectSource(source.id)"
            >
              <div class="source-icon">
                <svg v-if="source.type === 'pdf'" width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="#e53935" stroke-width="1.5"/>
                  <text x="7" y="17" font-size="6" fill="#e53935">PDF</text>
                </svg>
                <svg v-else-if="source.type === 'link'" width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="9" stroke="#1a73e8" stroke-width="1.5"/>
                  <path d="M10.5 13.5a1.5 1.5 0 0 0 2.12 2.12M13.5 10.5a1.5 1.5 0 0 1-2.12-2.12" stroke="#1a73e8" stroke-width="1.5"/>
                </svg>
                <svg v-else width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="#757575" stroke-width="1.5"/>
                </svg>
              </div>
              <div class="source-info">
                <span class="source-name">{{ source.name }}</span>
                <span class="source-meta">{{ formatSize(source.size) }} · {{ source.chunk_count }} 个片段</span>
              </div>
              <button class="source-delete" @click.stop="deleteSource(source.id)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                  <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 检索/对话面板 -->
      <div class="chat-panel">
        <div class="panel-section">
          <div class="section-header">
            <h3>检索 & 对话</h3>
          </div>
          
          <!-- 检索输入 -->
          <div class="search-box">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
              <circle cx="11" cy="11" r="7" stroke="currentColor" stroke-width="2"/>
              <path d="M21 21l-4.35-4.35" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
            <input 
              v-model="query" 
              type="text" 
              placeholder="向知识库提问..."
              @keyup.enter="search"
            />
            <button v-if="query" class="clear-btn" @click="query = ''">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
              </svg>
            </button>
          </div>

          <!-- 对话/检索结果 -->
          <div class="chat-messages" ref="messagesContainer">
            <div v-if="messages.length === 0" class="empty-state">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" stroke="currentColor" stroke-width="1.5"/>
              </svg>
              <p>开始向你的知识库提问</p>
              <span>基于来源获得带有引用的回答</span>
            </div>
            
            <div 
              v-for="(msg, index) in messages" 
              :key="index"
              class="message"
              :class="msg.role"
            >
              <div class="message-avatar">
                <svg v-if="msg.role === 'user'" width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="8" r="4" stroke="currentColor" stroke-width="2"/>
                  <path d="M4 20c0-4 4-6 8-6s8 2 8 6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                </svg>
                <svg v-else width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 0 1 2-2z" stroke="currentColor" stroke-width="2"/>
                </svg>
              </div>
              <div class="message-content">
                <p>{{ msg.content }}</p>
                <!-- 引用展示 -->
                <div v-if="msg.citations && msg.citations.length > 0" class="citations">
                  <span class="citations-label">来源引用：</span>
                  <div class="citation-chips">
                    <span 
                      v-for="(cite, cIndex) in msg.citations" 
                      :key="cIndex"
                      class="citation-chip"
                      @click="scrollToSource(cite.sourceId)"
                    >
                      {{ cite.sourceName }} - {{ cite.chunk }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 输出面板 -->
      <div class="output-panel">
        <div class="panel-section">
          <div class="section-header">
            <h3>输出</h3>
          </div>
          
          <!-- Studio 功能卡片 -->
          <div class="studio-cards">
            <div class="studio-card" @click="createAudioOverview">
              <div class="card-icon audio">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                  <path d="M3 18v-6a9 9 0 0 1 18 0v6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                  <path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3v5zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3v5z" stroke="currentColor" stroke-width="2"/>
                </svg>
              </div>
              <h4>音频概览</h4>
              <p>将知识转化为双人对话播客</p>
            </div>
            
            <div class="studio-card" @click="createMindMap">
              <div class="card-icon mindmap">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="2"/>
                  <circle cx="4" cy="6" r="2" stroke="currentColor" stroke-width="2"/>
                  <circle cx="20" cy="6" r="2" stroke="currentColor" stroke-width="2"/>
                  <circle cx="4" cy="18" r="2" stroke="currentColor" stroke-width="2"/>
                  <circle cx="20" cy="18" r="2" stroke="currentColor" stroke-width="2"/>
                  <path d="M9.5 10.5L5.5 7M14.5 10.5l4-3.5M9.5 13.5l-4 3.5M14.5 13.5l4 3.5" stroke="currentColor" stroke-width="1.5"/>
                </svg>
              </div>
              <h4>思维导图</h4>
              <p>可视化主题关系和结构</p>
            </div>
            
            <div class="studio-card" @click="createReport">
              <div class="card-icon report">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="currentColor" stroke-width="2"/>
                  <path d="M14 2v6h6M8 13h8M8 17h8M8 9h2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                </svg>
              </div>
              <h4>学习指南</h4>
              <p>生成结构化的研究报告</p>
            </div>
            
            <div class="studio-card" @click="createTimeline">
              <div class="card-icon timeline">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                  <path d="M12 8v8l4 4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                  <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2"/>
                  <path d="M12 3v3M12 18v3M3 12h3M18 12h3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                </svg>
              </div>
              <h4>时间线</h4>
              <p>从文档中提取时间线事件</p>
            </div>
          </div>

          <!-- 最近活动 -->
          <div class="recent-activity">
            <h4>最近更新</h4>
            <div class="activity-list">
              <div v-for="activity in recentActivities" :key="activity.id" class="activity-item">
                <span class="activity-icon" :class="activity.type"></span>
                <div class="activity-info">
                  <span class="activity-title">{{ activity.title }}</span>
                  <span class="activity-time">{{ activity.time }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Studio 弹窗 -->
    <div v-if="showStudio" class="studio-modal" @click.self="showStudio = false">
      <div class="studio-modal-content">
        <div class="studio-modal-header">
          <h3>创建输出</h3>
          <button class="close-btn" @click="showStudio = false">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </button>
        </div>
        <div class="studio-modal-body">
          <p>选择输出类型开始生成</p>
        </div>
      </div>
    </div>

    <!-- 添加来源选项弹窗 -->
    <div v-if="showAddOptions" class="add-options-modal" @click.self="showAddOptions = false">
      <div class="add-options-content">
        <div class="add-option" @click="handleAddFile">
          <div class="option-icon upload">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
              <polyline points="17,8 12,3 7,8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <line x1="12" y1="3" x2="12" y2="15" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </div>
          <div class="option-text">
            <h4>上传文件</h4>
            <p>支持 TXT、MD、PDF、Word</p>
          </div>
        </div>
        <div class="add-option" @click="showTextModal = true; showAddOptions = false">
          <div class="option-icon text">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="currentColor" stroke-width="2"/>
              <polyline points="14,2 14,8 20,8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <line x1="16" y1="13" x2="8" y2="13" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
              <line x1="16" y1="17" x2="8" y2="17" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </div>
          <div class="option-text">
            <h4>输入文本</h4>
            <p>直接粘贴或输入文字内容</p>
          </div>
        </div>
        <div class="add-option" @click="showLinkModal = true; showAddOptions = false">
          <div class="option-icon link">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          <div class="option-text">
            <h4>添加链接</h4>
            <p>从网页提取内容</p>
          </div>
        </div>
      </div>
    </div>

    <!-- 文本输入弹窗 -->
    <div v-if="showTextModal" class="text-modal" @click.self="showTextModal = false">
      <div class="text-modal-content">
        <div class="text-modal-header">
          <h3>添加文本</h3>
          <button class="close-btn" @click="showTextModal = false">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </button>
        </div>
        <div class="text-modal-body">
          <div class="form-group">
            <label>标题</label>
            <input
              v-model="textName"
              type="text"
              placeholder="为这段文本起个名字"
            />
          </div>
          <div class="form-group">
            <label>内容</label>
            <textarea
              v-model="textContent"
              placeholder="粘贴或输入要添加的文本内容..."
              rows="10"
            ></textarea>
          </div>
          <div class="text-modal-actions">
            <button class="btn-cancel" @click="showTextModal = false">取消</button>
            <button class="btn-submit" @click="submitText" :disabled="!textName.trim() || !textContent.trim() || isUploading">
              {{ isUploading ? '处理中...' : '添加' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 链接输入弹窗 -->
    <div v-if="showLinkModal" class="text-modal" @click.self="showLinkModal = false">
      <div class="text-modal-content">
        <div class="text-modal-header">
          <h3>添加链接</h3>
          <button class="close-btn" @click="showLinkModal = false">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </button>
        </div>
        <div class="text-modal-body">
          <div class="form-group">
            <label>网页链接</label>
            <input
              v-model="linkUrl"
              type="url"
              placeholder="输入网页链接 URL"
            />
          </div>
          <div class="text-modal-actions">
            <button class="btn-cancel" @click="showLinkModal = false">取消</button>
            <button class="btn-submit" @click="submitLink" :disabled="!linkUrl.trim() || isUploading">
              {{ isUploading ? '处理中...' : '添加' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import {
  getSources,
  uploadSource,
  addLink,
  addTextSource,
  deleteSource as apiDeleteSource,
  searchKnowledge,
  chatWithKnowledge,
  getKbStats
} from '../api/knowledge'

export default {
  name: 'KnowledgeDraftPanel',
  data() {
    return {
      isDragOver: false,
      query: '',
      activeSource: null,
      showStudio: false,
      isLoading: false,
      isUploading: false,
      // 真实数据
      sources: [],
      messages: [],
      recentActivities: [],
      totalChunks: 0,
      // 文件上传输入
      fileInput: null,
      // 链接输入
      showLinkModal: false,
      linkUrl: '',
      // 文本输入弹窗
      showTextModal: false,
      textName: '',
      textContent: '',
      // 添加选项菜单
      showAddOptions: false,
    }
  },
  mounted() {
    this.loadSources()
    this.loadStats()
  },
  methods: {
    // 加载来源列表
    async loadSources() {
      try {
        this.isLoading = true
        const data = await getSources()
        this.sources = data.sources || []
        this.totalChunks = data.total_chunks || 0
      } catch (e) {
        console.error('加载来源失败:', e)
      } finally {
        this.isLoading = false
      }
    },
    
    // 加载统计信息
    async loadStats() {
      try {
        const stats = await getKbStats()
        this.recentActivities = [
          { id: 1, type: 'index', title: `共 ${stats.total_chunks} 个知识片段`, time: '当前' },
          { id: 2, type: 'upload', title: `共 ${stats.total_sources} 个知识来源`, time: '当前' },
        ]
      } catch (e) {
        console.error('加载统计失败:', e)
      }
    },
    
    // 触发文件选择
    addSource() {
      this.showAddOptions = true
    },

    // 处理上传文件
    handleAddFile() {
      this.showAddOptions = false
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = '.txt,.md,.pdf,.doc,.docx'
      input.onchange = async (e) => {
        const file = e.target.files?.[0]
        if (file) {
          await this.handleFileUpload(file)
        }
      }
      input.click()
    },
    
    // 处理文件上传
    async handleFileUpload(file) {
      try {
        this.isUploading = true
        const result = await uploadSource(file)
        if (result.success) {
          this.sources.unshift(result.source)
          this.totalChunks += result.source.chunk_count
          this.recentActivities.unshift({
            id: Date.now(),
            type: 'upload',
            title: `上传了 ${file.name}`,
            time: '刚刚'
          })
        }
      } catch (e) {
        console.error('上传失败:', e)
        alert('上传失败: ' + e.message)
      } finally {
        this.isUploading = false
      }
    },
    
    // 处理拖拽上传
    async handleDrop(e) {
      this.isDragOver = false
      const files = e.dataTransfer.files
      if (files.length > 0) {
        await this.handleFileUpload(files[0])
      }
    },
    
    // 添加链接
    async submitLink() {
      if (!this.linkUrl.trim()) return
      
      try {
        this.isUploading = true
        const result = await addLink(this.linkUrl)
        if (result.success) {
          this.sources.unshift(result.source)
          this.totalChunks += result.source.chunk_count
          this.recentActivities.unshift({
            id: Date.now(),
            type: 'upload',
            title: `添加了链接`,
            time: '刚刚'
          })
          this.showLinkModal = false
          this.linkUrl = ''
        }
      } catch (e) {
        console.error('添加链接失败:', e)
        alert('添加链接失败: ' + e.message)
      } finally {
        this.isUploading = false
      }
    },

    // 提交文本内容
    async submitText() {
      if (!this.textName.trim() || !this.textContent.trim()) return
      
      try {
        this.isUploading = true
        const result = await addTextSource(this.textName.trim(), this.textContent.trim())
        if (result.success) {
          this.sources.unshift(result.source)
          this.totalChunks += result.source.chunk_count
          this.recentActivities.unshift({
            id: Date.now(),
            type: 'upload',
            title: `添加了文本: ${this.textName}`,
            time: '刚刚'
          })
          this.showTextModal = false
          this.textName = ''
          this.textContent = ''
        }
      } catch (e) {
        console.error('添加文本失败:', e)
        alert('添加文本失败: ' + e.message)
      } finally {
        this.isUploading = false
      }
    },
    
    selectSource(id) {
      this.activeSource = this.activeSource === id ? null : id
    },
    
    // 删除来源
    async deleteSource(id) {
      if (!confirm('确定要删除这个知识来源吗？')) return
      
      try {
        await apiDeleteSource(id)
        const source = this.sources.find(s => s.id === id)
        if (source) {
          this.totalChunks -= source.chunk_count
        }
        this.sources = this.sources.filter(s => s.id !== id)
        this.recentActivities.unshift({
          id: Date.now(),
          type: 'index',
          title: `删除了知识来源`,
          time: '刚刚'
        })
      } catch (e) {
        console.error('删除失败:', e)
        alert('删除失败: ' + e.message)
      }
    },
    
    // 搜索/对话
    async search() {
      if (!this.query.trim() || this.isLoading) return
      
      const userQuery = this.query.trim()
      this.query = ''
      
      // 添加用户消息
      this.messages.push({
        role: 'user',
        content: userQuery
      })
      
      // 添加加载中的助手消息
      const loadingMsg = {
        role: 'assistant',
        content: '正在思考...',
        citations: []
      }
      this.messages.push(loadingMsg)
      
      try {
        this.isLoading = true
        
        // 转换为历史格式
        const history = this.messages
          .filter(m => m.role !== 'assistant' || m !== loadingMsg)
          .slice(-10)
          .map(m => ({ role: m.role, content: m.content }))
        
        const result = await chatWithKnowledge(userQuery, history)
        
        // 更新助手消息
        loadingMsg.content = result.answer
        loadingMsg.citations = result.citations.map(c => ({
          sourceId: c.source_id,
          sourceName: c.source_name,
          chunk: c.chunk
        }))
        
        // 添加到活动记录
        this.recentActivities.unshift({
          id: Date.now(),
          type: 'chat',
          title: `对话: ${userQuery.slice(0, 20)}...`,
          time: '刚刚'
        })
        
      } catch (e) {
        console.error('对话失败:', e)
        loadingMsg.content = '对话失败: ' + e.message
      } finally {
        this.isLoading = false
      }
    },
    
    scrollToSource(sourceId) {
      this.activeSource = sourceId
    },
    
    openStudio() {
      if (this.sources.length === 0) {
        alert('请先添加知识来源')
        return
      }
      this.showStudio = true
    },
    
    createAudioOverview() {
      alert('音频概览功能开发中...')
    },
    
    createMindMap() {
      alert('思维导图功能开发中...')
    },
    
    createReport() {
      alert('学习指南功能开发中...')
    },
    
    createTimeline() {
      alert('时间线功能开发中...')
    },
    
    // 格式化文件大小
    formatSize(bytes) {
      if (!bytes) return '0 B'
      if (bytes < 1024) return bytes + ' B'
      if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
      return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
    }
  }
}
</script>

<style scoped>
.notebooklm-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary, #f8f9fa);
  padding: 16px;
  gap: 16px;
}

/* 顶部标题栏 */
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--bg-secondary, #fff);
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo-icon {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 10px;
  color: white;
}

.header-left h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary, #1f1f1f);
}

.source-count {
  font-size: 13px;
  color: var(--text-muted, #666);
  background: var(--bg-primary, #f0f0f0);
  padding: 4px 10px;
  border-radius: 20px;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.action-btn.primary {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.action-btn.primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

/* 三面板布局 */
.panels-container {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 280px 1fr 300px;
  gap: 16px;
}

.panel-section {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-secondary, #fff);
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  overflow: hidden;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border, #eee);
}

.section-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #1f1f1f);
}

.add-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px solid var(--border, #ddd);
  border-radius: 6px;
  background: transparent;
  font-size: 12px;
  color: var(--text-secondary, #666);
  cursor: pointer;
  transition: all 0.2s ease;
}

.add-btn:hover {
  border-color: #667eea;
  color: #667eea;
}

/* 来源面板 */
.source-panel {
  display: flex;
  flex-direction: column;
}

.drop-zone {
  margin: 12px;
  padding: 24px;
  border: 2px dashed var(--border, #ddd);
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: var(--text-muted, #999);
  transition: all 0.2s ease;
}

.drop-zone.drag-over {
  border-color: #667eea;
  background: rgba(102, 126, 234, 0.05);
  color: #667eea;
}

.drop-zone.uploading {
  opacity: 0.7;
  pointer-events: none;
}

.spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.drop-zone p {
  margin: 0;
  font-size: 13px;
  font-weight: 500;
}

.drop-zone span {
  font-size: 11px;
}

.source-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.source-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.source-item:hover {
  background: var(--bg-primary, #f5f5f5);
}

.source-item.active {
  background: rgba(102, 126, 234, 0.1);
}

.source-icon {
  flex-shrink: 0;
}

.source-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.source-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary, #1f1f1f);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.source-meta {
  font-size: 11px;
  color: var(--text-muted, #999);
}

.source-delete {
  opacity: 0;
  padding: 4px;
  border: none;
  background: transparent;
  color: var(--text-muted, #999);
  cursor: pointer;
  transition: all 0.15s ease;
}

.source-item:hover .source-delete {
  opacity: 1;
}

.source-delete:hover {
  color: #e53935;
}

/* 检索/对话面板 */
.chat-panel {
  display: flex;
  flex-direction: column;
}

.search-box {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 12px;
  padding: 10px 14px;
  background: var(--bg-primary, #f5f5f5);
  border-radius: 10px;
  color: var(--text-muted, #999);
}

.search-box input {
  flex: 1;
  border: none;
  background: transparent;
  font-size: 14px;
  color: var(--text-primary, #1f1f1f);
  outline: none;
}

.search-box input::placeholder {
  color: var(--text-muted, #999);
}

.clear-btn {
  padding: 2px;
  border: none;
  background: transparent;
  color: var(--text-muted, #999);
  cursor: pointer;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--text-muted, #999);
}

.empty-state p {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
}

.empty-state span {
  font-size: 12px;
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  color: var(--text-muted, #999);
}

.empty-source-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 20px;
  text-align: center;
  color: var(--text-muted, #999);
}

.empty-source-state p {
  margin: 0;
  font-size: 13px;
}

.empty-source-state span {
  font-size: 11px;
  margin-top: 4px;
}

.message {
  display: flex;
  gap: 10px;
}

.message-avatar {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--bg-primary, #f0f0f0);
  color: var(--text-muted, #999);
}

.message.user .message-avatar {
  background: #667eea;
  color: white;
}

.message-content {
  flex: 1;
  min-width: 0;
}

.message-content p {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-primary, #1f1f1f);
  white-space: pre-wrap;
}

.citations {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--border, #eee);
}

.citations-label {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-muted, #999);
}

.citation-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.citation-chip {
  padding: 4px 10px;
  background: rgba(102, 126, 234, 0.1);
  border-radius: 20px;
  font-size: 11px;
  color: #667eea;
  cursor: pointer;
  transition: all 0.15s ease;
}

.citation-chip:hover {
  background: rgba(102, 126, 234, 0.2);
}

/* 输出面板 */
.output-panel {
  display: flex;
  flex-direction: column;
}

.studio-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  padding: 12px;
}

.studio-card {
  padding: 14px;
  background: var(--bg-primary, #f5f5f5);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.studio-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}

.card-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  margin-bottom: 10px;
}

.card-icon.audio {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
  color: white;
}

.card-icon.mindmap {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
  color: white;
}

.card-icon.report {
  background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
  color: white;
}

.card-icon.timeline {
  background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
  color: white;
}

.studio-card h4 {
  margin: 0 0 4px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #1f1f1f);
}

.studio-card p {
  margin: 0;
  font-size: 11px;
  color: var(--text-muted, #999);
  line-height: 1.4;
}

.recent-activity {
  flex: 1;
  padding: 12px;
  border-top: 1px solid var(--border, #eee);
  overflow-y: auto;
}

.recent-activity h4 {
  margin: 0 0 12px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #1f1f1f);
}

.activity-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.activity-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  border-radius: 6px;
  transition: background 0.15s ease;
}

.activity-item:hover {
  background: var(--bg-primary, #f5f5f5);
}

.activity-icon {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.activity-icon.upload {
  background: #4facfe;
}

.activity-icon.index {
  background: #43e97b;
}

.activity-icon.chat {
  background: #fa709a;
}

.activity-icon.audio {
  background: #f093fb;
}

.activity-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.activity-title {
  font-size: 12px;
  color: var(--text-primary, #1f1f1f);
}

.activity-time {
  font-size: 10px;
  color: var(--text-muted, #999);
}

/* Studio 弹窗 */
.studio-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.studio-modal-content {
  width: 90%;
  max-width: 500px;
  background: var(--bg-secondary, #fff);
  border-radius: 16px;
  overflow: hidden;
  animation: modalIn 0.2s ease;
}

@keyframes modalIn {
  from {
    opacity: 0;
    transform: scale(0.95);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

.studio-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border, #eee);
}

.studio-modal-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.close-btn {
  padding: 4px;
  border: none;
  background: transparent;
  color: var(--text-muted, #999);
  cursor: pointer;
}

.studio-modal-body {
  padding: 24px;
  text-align: center;
}

.studio-modal-body p {
  margin: 0;
  color: var(--text-secondary, #666);
}

/* 添加选项弹窗 */
.add-options-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.add-options-content {
  width: 90%;
  max-width: 400px;
  background: var(--bg-secondary, #fff);
  border-radius: 16px;
  padding: 8px;
  animation: modalIn 0.2s ease;
}

.add-option {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.add-option:hover {
  background: var(--bg-primary, #f5f5f5);
}

.option-icon {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
}

.option-icon.upload {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.option-icon.text {
  background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
  color: white;
}

.option-icon.link {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
  color: white;
}

.option-text h4 {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary, #1f1f1f);
}

.option-text p {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted, #999);
}

/* 文本输入弹窗 */
.text-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.text-modal-content {
  width: 90%;
  max-width: 600px;
  background: var(--bg-secondary, #fff);
  border-radius: 16px;
  overflow: hidden;
  animation: modalIn 0.2s ease;
}

.text-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border, #eee);
}

.text-modal-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.text-modal-body {
  padding: 20px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary, #1f1f1f);
}

.form-group input {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--border, #ddd);
  border-radius: 8px;
  font-size: 14px;
  color: var(--text-primary, #1f1f1f);
  outline: none;
  transition: border-color 0.2s ease;
  box-sizing: border-box;
}

.form-group input:focus {
  border-color: #667eea;
}

.form-group textarea {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--border, #ddd);
  border-radius: 8px;
  font-size: 14px;
  color: var(--text-primary, #1f1f1f);
  outline: none;
  transition: border-color 0.2s ease;
  resize: vertical;
  min-height: 200px;
  font-family: inherit;
  box-sizing: border-box;
}

.form-group textarea:focus {
  border-color: #667eea;
}

.text-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
}

.btn-cancel {
  padding: 10px 20px;
  border: 1px solid var(--border, #ddd);
  border-radius: 8px;
  background: transparent;
  font-size: 14px;
  color: var(--text-secondary, #666);
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-cancel:hover {
  background: var(--bg-primary, #f5f5f5);
}

.btn-submit {
  padding: 10px 24px;
  border: none;
  border-radius: 8px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  font-size: 14px;
  font-weight: 500;
  color: white;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-submit:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.btn-submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
