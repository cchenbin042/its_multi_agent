<template>
  <div class="message-item" :class="message.role">
    <div class="avatar">
      <el-avatar
        :icon="message.role === 'user' ? User : Service"
        :style="{ backgroundColor: message.role === 'user' ? '#409EFF' : '#00f260' }"
      />
    </div>
    <div class="content">
      <!-- Assistant 消息：先显示检索步骤，再显示回答内容 -->
      <template v-if="message.role === 'assistant'">
        <!-- Agent 推理步骤区域 -->
        <AgentSteps
          v-if="message.mode === 'agent' && message.agentRounds?.length"
          :rounds="message.agentRounds"
          :total-duration="message.totalDurationMs"
        />

        <!-- 检索步骤区域 -->
        <RetrievalSteps
          v-else-if="hasSteps"
          :steps="message.steps"
          :total-duration="message.totalDurationMs"
          :loading="message.loading"
          :timer="timer"
          v-model:collapsed="stepsCollapsed"
          @toggle-step="handleToggleStep"
        />

        <!-- 回答内容 -->
        <div class="bubble">
          <!-- 流式输出中：纯文本 -->
          <div v-if="isStreaming" class="raw-text">{{ message.content }}</div>
          <!-- 加载中状态 -->
          <div v-else-if="message.loading && !message.content" class="typing-indicator">
            <span></span><span></span><span></span>
          </div>
          <!-- 完成后：Markdown 渲染 -->
          <div v-else-if="message.content" v-html="sanitizedHtml"></div>
        </div>

        <!-- 参考来源 -->
        <div v-if="message.sources?.length && !message.loading" class="sources">
          <span class="sources-label">参考资料:</span>
          <span v-for="(source, idx) in highlightedSources" :key="idx" class="source-tag" v-html="source" />
        </div>

      </template>

      <!-- User 消息 -->
      <template v-else>
        <div class="bubble">
          <div v-html="formatContent(message.content)"></div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, inject, watch } from 'vue'
import { User, Service } from '@element-plus/icons-vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import RetrievalSteps from './RetrievalSteps.vue'
import AgentSteps from './AgentSteps.vue'

const props = defineProps({
  message: {
    type: Object,
    required: true
  },
  timer: {
    type: Object,
    default: () => ({ formatted: { value: '0.0s' } })
  }
})

const emit = defineEmits(['toggle-step'])

// 步骤区折叠状态
const stepsCollapsed = ref(false)

// 判断是否有步骤数据
const hasSteps = computed(() => {
  return props.message.steps && props.message.steps.length > 0
})

// 判断是否正在流式输出
const isStreaming = computed(() => {
  // Agent 模式：loading 由 onComplete 解除，期间有内容即为流式输出
  if (props.message.mode === 'agent') {
    return props.message.loading && !!props.message.content
  }
  if (!hasSteps.value) return false
  const answerStep = props.message.steps.find(s => s.key === 'answer_generation')
  return answerStep?.status === 'running'
})

// 调试：监听 message 变化
watch(() => props.message, (newVal) => {
  console.log('[DEBUG MessageItem] message updated:', newVal.id, 'content:', newVal.content?.length || 0, 'loading:', newVal.loading)
}, { deep: true })

// 关键词高亮
const highlightKeywords = (html, keywords) => {
  if (!html || !keywords || keywords.length === 0) return html
  // 只在文本节点中高亮，避免破坏 HTML 标签
  const pattern = keywords
    .map(k => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
    .join('|')
  if (!pattern) return html
  const regex = new RegExp(`(?<!<[^>]*)(${pattern})`, 'gi')
  return html.replace(regex, '<mark class="kw-highlight">$1</mark>')
}

// 安全的 HTML 渲染
const sanitizedHtml = computed(() => {
  if (!props.message.content) return ''
  const html = DOMPurify.sanitize(marked(props.message.content))
  return highlightKeywords(html, props.message.matchedKeywords || [])
})

// 高亮后的来源标签
const highlightedSources = computed(() => {
  if (!props.message.sources) return []
  const keywords = props.message.matchedKeywords || []
  return props.message.sources.map(s => highlightKeywords(s, keywords))
})

// User 消息的 Markdown 渲染
const formatContent = (text) => {
  if (!text) return ''
  return DOMPurify.sanitize(marked(text))
}

const handleToggleStep = (stepKey) => {
  emit('toggle-step', stepKey)
}
</script>

<style lang="scss" scoped>
.message-item {
  display: flex;
  margin-bottom: 20px;

  &.user {
    flex-direction: row-reverse;

    .content {
      align-items: flex-end;

      .bubble {
        background-color: #409eff;
        color: #fff;
        border-top-right-radius: 0;
      }
    }

    .avatar {
      margin-left: 10px;
      margin-right: 0;
    }
  }

  &.assistant {
    .content {
      align-items: flex-start;

      .bubble {
        background-color: #1f242d;
        color: #c9d1d9;
        border: 1px solid #30363d;
        border-top-left-radius: 0;
      }
    }

    .avatar {
      margin-right: 10px;
    }
  }
}

.content {
  display: flex;
  flex-direction: column;
  max-width: 70%;
}

.bubble {
  padding: 10px 15px;
  border-radius: 12px;
  line-height: 1.6;
  font-size: 14px;
  word-break: break-word;

  /* Markdown 样式适配 */
  :deep(p) {
    margin: 0 0 10px 0;

    &:last-child {
      margin-bottom: 0;
    }
  }

  :deep(a) {
    color: #58a6ff;
    text-decoration: none;

    &:hover {
      text-decoration: underline;
    }
  }

  :deep(ul),
  :deep(ol) {
    padding-left: 20px;
    margin: 5px 0;
  }

  :deep(code) {
    background-color: rgba(110, 118, 129, 0.4);
    padding: 0.2em 0.4em;
    border-radius: 6px;
    font-family: monospace;
  }

  :deep(pre) {
    background-color: #161b22;
    padding: 10px;
    border-radius: 6px;
    overflow-x: auto;

    code {
      background-color: transparent;
      padding: 0;
    }
  }

  :deep(img) {
    max-width: 100%;
    border-radius: 6px;
    margin: 10px 0;
  }

  :deep(table) {
    border-collapse: collapse;
    width: 100%;
    margin: 10px 0;

    th,
    td {
      border: 1px solid #30363d;
      padding: 8px 12px;
      text-align: left;
    }

    th {
      background-color: #21262d;
    }
  }

  :deep(mark.kw-highlight) {
    background-color: rgba(255, 213, 0, 0.35);
    color: #ffd54f;
    border-radius: 2px;
    padding: 0 2px;
  }
}

.raw-text {
  white-space: pre-wrap;
  word-break: break-word;
}

.sources {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
  padding-left: 4px;
}

.sources-label {
  font-size: 12px;
  color: #8b949e;
}

.source-tag {
  background-color: rgba(63, 185, 80, 0.1);
  border: 1px solid rgba(63, 185, 80, 0.2);
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 12px;
  color: #3fb950;

  :deep(mark.kw-highlight) {
    background-color: rgba(255, 213, 0, 0.35);
    color: inherit;
    border-radius: 2px;
    padding: 0 2px;
  }
}

.typing-indicator {
  span {
    display: inline-block;
    width: 6px;
    height: 6px;
    background-color: #8b949e;
    border-radius: 50%;
    margin: 0 2px;
    animation: bounce 1.4s infinite ease-in-out both;

    &:nth-child(1) {
      animation-delay: -0.32s;
    }
    &:nth-child(2) {
      animation-delay: -0.16s;
    }
  }
}

@keyframes bounce {
  0%,
  80%,
  100% {
    transform: scale(0);
  }
  40% {
    transform: scale(1);
  }
}
</style>