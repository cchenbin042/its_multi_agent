<template>
  <div class="chat-container">
    <!-- 对话区域（全宽） -->
    <div class="chat-box">
      <!-- 顶栏 -->
      <div class="chat-topbar">
        <el-button
          class="history-toggle"
          :icon="Clock"
          circle
          size="small"
          @click="sidebarOpen = !sidebarOpen"
          title="历史对话"
        />
        <span class="topbar-title">ITS 智能助手</span>
        <el-button
          class="new-chat-btn"
          @click="handleNewChat"
          :disabled="loading"
          size="small"
        >
          <el-icon><Plus /></el-icon> 新对话
        </el-button>
      </div>

      <div class="messages" ref="messagesRef">
        <div v-if="messages.length === 0" class="empty-state">
          <el-icon :size="60" color="#30363d"><ChatDotRound /></el-icon>
          <p>开始您的提问，我将基于知识库为您解答。</p>
        </div>

        <MessageItem
          v-for="msg in messages"
          :key="msg.id"
          :message="msg"
          :timer="msg.role === 'assistant' && msg.loading ? timer : {}"
          @toggle-step="handleToggleStep(msg.id, $event)"
        />
      </div>

      <div class="input-area">
        <el-input
          v-model="input"
          placeholder="请输入您的问题..."
          :rows="3"
          type="textarea"
          resize="none"
          @keydown.enter.prevent="handleSend"
        />
        <el-switch
          v-model="deepMode"
          active-text="深度"
          inactive-text="快速"
          class="deep-mode-switch"
        />
        <el-button
          type="primary"
          class="send-btn"
          @click="handleSend"
          :loading="loading"
          :disabled="!input.trim()"
        >
          <el-icon><Position /></el-icon> 发送
        </el-button>
      </div>
    </div>

    <!-- 遮罩层 -->
    <div
      class="sidebar-backdrop"
      :class="{ visible: sidebarOpen }"
      @click="sidebarOpen = false"
    />

    <!-- 历史对话浮层 -->
    <div class="history-overlay" :class="{ open: sidebarOpen }">
      <div class="overlay-header">
        <span>历史对话</span>
        <el-button :icon="'Close'" size="small" text @click="sidebarOpen = false" />
      </div>
      <div class="overlay-list">
        <div
          v-for="conv in conversations"
          :key="conv.session_id"
          class="overlay-item"
          :class="{ active: conv.session_id === sessionId }"
          @click="loadConversation(conv.session_id); sidebarOpen = false"
        >
          <div class="conv-preview">{{ conv.preview || '新对话' }}</div>
          <div class="conv-meta">
            <span>{{ conv.msg_count }} 个问题</span>
            <span>{{ conv.started_at?.slice(0, 10) }}</span>
          </div>
          <el-button
            class="conv-delete"
            :icon="'Delete'"
            size="small"
            text
            @click.stop="handleDeleteConversation(conv.session_id)"
          />
        </div>
        <div v-if="conversations.length === 0" class="sidebar-empty">
          暂无历史对话
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, onUnmounted } from 'vue'
import { queryKnowledgeStream, queryKnowledgeAgent, getConversations, getConversationMessages, deleteConversation } from '@/api/knowledge'
import { useTimer } from '@/composables/useTimer'
import { Position, ChatDotRound, Plus, Clock } from '@element-plus/icons-vue'
import MessageItem from '@/components/MessageItem.vue'

// 步骤定义
const STEP_DEFINITIONS = [
  { key: 'query_understanding', label: '查询理解' },
  { key: 'knowledge_retrieval', label: '知识检索' },
  { key: 'reranking', label: '精排筛选' },
  { key: 'web_search', label: '网络搜索' },
  { key: 'answer_generation', label: '生成回答' }
]

// 生成唯一 ID
function generateId() {
  return `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
}

// 创建 assistant 消息模板
function createAssistantMessage() {
  return {
    id: generateId(),
    role: 'assistant',
    content: '',
    loading: true,
    steps: STEP_DEFINITIONS.map(def => ({
      ...def,
      status: 'pending',
      durationMs: 0,
      detail: {},
      collapsed: true
    })),
    sources: [],
    totalDurationMs: 0
  }
}

// 创建 agent 深度推理消息模板
function createAgentMessage() {
  return {
    id: generateId(),
    role: 'assistant',
    content: '',
    loading: true,
    mode: 'agent',
    agentRounds: [],
    sources: [],
    totalDurationMs: 0
  }
}

const input = ref('')
const loading = ref(false)
const messages = ref([])
const messagesRef = ref(null)
const sessionId = ref(`session-${Date.now()}`)
const deepMode = ref(false)
const timer = useTimer()
let abortController = null

// 历史对话浮层
const conversations = ref([])
const sidebarOpen = ref(false)

const fetchConversations = async () => {
  try {
    conversations.value = await getConversations(20)
  } catch (e) {
    console.error('Failed to fetch conversations:', e)
  }
}

const loadConversation = async (sid) => {
  if (loading.value) return
  sessionId.value = sid
  try {
    const msgs = await getConversationMessages(sid)
    messages.value = msgs.map(m => ({
      id: generateId(),
      role: m.role,
      content: m.content,
      loading: false,
    }))
    scrollToBottom()
  } catch (e) {
    console.error('Failed to load conversation:', e)
  }
}

const handleDeleteConversation = async (sid) => {
  try {
    await deleteConversation(sid)
    if (sessionId.value === sid) {
      handleNewChat()
    }
    fetchConversations()
  } catch (e) {
    console.error('Failed to delete conversation:', e)
  }
}

// 组件卸载时清理
onUnmounted(() => {
  if (abortController) {
    abortController()
    abortController = null
  }
})

onMounted(() => {
  fetchConversations()
})

const scrollToBottom = () => {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

const handleNewChat = () => {
  sessionId.value = `session-${Date.now()}`
  messages.value = []
  fetchConversations()
}

const handleSend = async () => {
  if (!input.value.trim() || loading.value) return

  // 取消之前未完成的请求
  if (abortController) {
    abortController()
    abortController = null
  }

  const question = input.value
  input.value = ''

  // Add user message
  messages.value.push({
    id: generateId(),
    role: 'user',
    content: question
  })
  scrollToBottom()

  // Add bot placeholder with steps
  loading.value = true
  timer.start()
  const botMessage = deepMode.value ? createAgentMessage() : createAssistantMessage()
  const botId = botMessage.id
  messages.value.push(botMessage)
  scrollToBottom()

  // 选择 API
  const streamApi = deepMode.value ? queryKnowledgeAgent : queryKnowledgeStream

  // 使用流式查询
  console.log('[DEBUG] Starting query, botId:', botId, 'deepMode:', deepMode.value)
  abortController = streamApi(
    { question, session_id: sessionId.value },
    {
      onStep: (stepData) => {
        console.log('[SSE] onStep received:', stepData)
        const botMsg = messages.value.find(m => m.id === botId)
        if (!botMsg) return

        if (botMsg.mode === 'agent') {
          const roundNum = stepData.detail?.round
          if (roundNum) {
            const existingIdx = botMsg.agentRounds.findIndex(r => r.round === roundNum)
            const roundData = {
              round: roundNum,
              status: stepData.status,
              tool_calls: stepData.detail?.tool_calls || [],
              final: stepData.detail?.final || false,
              reasoning: stepData.detail?.reasoning || '',
            }
            if (existingIdx >= 0) {
              botMsg.agentRounds.splice(existingIdx, 1, roundData)
            } else {
              botMsg.agentRounds.push(roundData)
            }
          }
          scrollToBottom()
          return
        }

        botMsg.loading = false
        const stepIdx = botMsg.steps.findIndex(s => s.key === stepData.step)
        if (stepIdx >= 0) {
          const uiStatus = stepData.status === 'started' ? 'running' : stepData.status
          const newStep = {
            ...botMsg.steps[stepIdx],
            status: uiStatus,
            durationMs: stepData.duration_ms || botMsg.steps[stepIdx].durationMs,
            detail: stepData.detail || botMsg.steps[stepIdx].detail,
            collapsed: uiStatus === 'completed' ? true : (uiStatus === 'running' ? false : botMsg.steps[stepIdx].collapsed)
          }
          botMsg.steps.splice(stepIdx, 1, newStep)
        }
        scrollToBottom()
      },

      onToken: (chunk) => {
        const botMsg = messages.value.find(m => m.id === botId)
        if (!botMsg) {
          console.error('[SSE] onToken: botMsg not found for id:', botId)
          return
        }
        botMsg.content += chunk
        scrollToBottom()
      },

      onComplete: (data) => {
        loading.value = false
        timer.stop()
        abortController = null
        const botMsg = messages.value.find(m => m.id === botId)
        if (!botMsg) return
        if (botMsg.mode === 'agent') {
          botMsg.agentRounds.forEach(r => { r.status = 'completed' })
        } else {
          botMsg.steps.forEach(s => {
            if (s.status === 'running') s.status = 'completed'
          })
        }
        botMsg.sources = data.sources || []
        botMsg.matchedKeywords = data.matched_keywords || []
        botMsg.totalDurationMs = data.total_duration_ms || 0
        botMsg.loading = false
        fetchConversations()
        scrollToBottom()
      },

      onError: (error) => {
        console.error('Stream error:', error)
        loading.value = false
        timer.stop()
        abortController = null
        const botMsg = messages.value.find(m => m.id === botId)
        if (!botMsg) return
        botMsg.loading = false
        botMsg.content = 'Sorry, an error occurred. Please try again later.'
        if (botMsg.mode === 'agent') {
          botMsg.agentRounds.forEach(r => {
            if (r.status === 'running') r.status = 'error'
          })
        } else {
          const runningStep = botMsg.steps.find(s => s.status === 'running')
          if (runningStep) runningStep.status = 'error'
        }
        scrollToBottom()
      }
    }
  )
}

// 处理步骤折叠切换
const handleToggleStep = (messageId, stepKey) => {
  const msg = messages.value.find(m => m.id === messageId)
  if (msg && msg.steps) {
    const step = msg.steps.find(s => s.key === stepKey)
    if (step) {
      step.collapsed = !step.collapsed
    }
  }
}

const handleCancel = () => {
  if (abortController) {
    abortController()
    abortController = null
    loading.value = false
    timer.stop()
    const botMsg = messages.value.findLast(m => m.role === 'assistant' && m.loading)
    if (botMsg) {
      botMsg.loading = false
      botMsg.content = 'Request cancelled.'
    }
  }
}
</script>

<style lang="scss" scoped>
.chat-container {
  height: calc(100vh - 40px);
  position: relative;
  display: flex;
}

.chat-box {
  flex: 1;
  background-color: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-topbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  background-color: #0d1117;
  border-bottom: 1px solid #30363d;
}

.history-toggle {
  flex-shrink: 0;
}

.topbar-title {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  color: #c9d1d9;
}

.new-chat-btn {
  flex-shrink: 0;
}

.messages {
  flex: 1;
  padding: 20px;
  overflow-y: auto;

  .empty-state {
    height: 100%;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    color: #8b949e;

    p {
      margin-top: 20px;
    }
  }
}

.input-area {
  padding: 20px;
  background-color: #0d1117;
  border-top: 1px solid #30363d;
  display: flex;
  gap: 10px;
  align-items: flex-end;

  :deep(.el-textarea__inner) {
    background-color: #161b22;
    border-color: #30363d;
    color: #c9d1d9;
    box-shadow: none;

    &:focus {
      border-color: #409eff;
    }
  }

  .deep-mode-switch {
    flex-shrink: 0;
    --el-switch-on-color: #f0883e;
    margin-right: 4px;
  }

  .send-btn {
    height: auto;
    padding: 10px 20px;
  }
}

// 遮罩层
.sidebar-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.25s;
  z-index: 10;
  border-radius: 8px;

  &.visible {
    opacity: 1;
    pointer-events: auto;
  }
}

// 历史对话浮层
.history-overlay {
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  width: 280px;
  background-color: #0d1117;
  display: flex;
  flex-direction: column;
  z-index: 20;
  transform: translateX(-100%);
  transition: transform 0.25s ease, visibility 0s 0.25s;
  visibility: hidden;

  &.open {
    transform: translateX(0);
    visibility: visible;
    transition: transform 0.25s ease, visibility 0s 0s;
    border-right: 1px solid #30363d;
    border-radius: 8px 0 0 8px;
    box-shadow: 4px 0 12px rgba(0, 0, 0, 0.3);
  }
}

.overlay-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  font-size: 15px;
  font-weight: 600;
  color: #c9d1d9;
  border-bottom: 1px solid #30363d;
  flex-shrink: 0;
}

.overlay-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.overlay-item {
  padding: 10px;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 4px;
  position: relative;
  border: 1px solid transparent;
  transition: background-color 0.15s;

  &:hover {
    background-color: #161b22;

    .conv-delete {
      display: flex;
    }
  }

  &.active {
    background-color: #1f242d;
    border-color: #30363d;
  }
}

.conv-preview {
  font-size: 13px;
  color: #c9d1d9;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  padding-right: 24px;
  line-height: 1.4;
}

.conv-meta {
  margin-top: 4px;
  font-size: 11px;
  color: #8b949e;
  display: flex;
  gap: 8px;
}

.conv-delete {
  position: absolute;
  top: 8px;
  right: 6px;
  display: none;
  color: #8b949e;

  &:hover {
    color: #f85149;
  }
}

.sidebar-empty {
  text-align: center;
  color: #8b949e;
  padding: 20px;
  font-size: 13px;
}
</style>
