import request from './request'

export function uploadFile(data) {
  return request({
    url: '/upload',
    method: 'post',
    data,
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

export function queryKnowledge(data) {
  return request({
    url: '/query',
    method: 'post',
    data
  })
}

export function submitFeedback(data) {
  return request({
    url: '/feedback',
    method: 'post',
    data
  })
}

export function getDocuments(params) {
  return request({ url: '/documents', method: 'get', params })
}

export function deleteDocument(title) {
  return request({ url: `/documents/${encodeURIComponent(title)}`, method: 'delete' })
}

export function getDocumentPreview(title) {
  return request({ url: `/documents/${encodeURIComponent(title)}`, method: 'get' })
}

export function getStats(days = 7) {
  return request({ url: '/stats', method: 'get', params: { days } })
}

export function getConversations(limit = 20) {
  return request({ url: '/conversations', method: 'get', params: { limit } })
}

export function getConversationMessages(sessionId) {
  return request({ url: `/conversations/${encodeURIComponent(sessionId)}`, method: 'get' })
}

export function deleteConversation(sessionId) {
  return request({ url: `/conversations/${encodeURIComponent(sessionId)}`, method: 'delete' })
}

export function getFeedbackStats(days = 7) {
  return request({ url: '/feedback/stats', method: 'get', params: { days } })
}

/**
 * Agent 深度推理模式流式查询（SSE）
 * 与 queryKnowledgeStream 相同的回调接口，但调用 /query/agent 端点
 */
export function queryKnowledgeAgent(data, callbacks) {
  const isDev = import.meta.env.DEV
  const baseUrl = isDev ? 'http://127.0.0.1:8001' : (import.meta.env.VITE_API_BASE_URL || '')
  const url = `${baseUrl}/query/agent`

  const controller = new AbortController()
  let isAborted = false
  let hasCompleted = false

  const safeCallback = (fn, ...args) => {
    if (!isAborted && fn) fn(...args)
  }

  const handleError = (error) => {
    if (error.name === 'AbortError' || isAborted) return
    safeCallback(callbacks.onError, error)
  }

  const handleEvent = (eventType, dataStr) => {
    if (!dataStr || !dataStr.trim()) return
    try {
      const parsed = JSON.parse(dataStr)
      switch (eventType) {
        case 'step':
          safeCallback(callbacks.onStep, parsed)
          break
        case 'token':
          safeCallback(callbacks.onToken, parsed.content)
          break
        case 'done':
          hasCompleted = true
          safeCallback(callbacks.onComplete, parsed)
          break
        default:
          if (parsed.step) safeCallback(callbacks.onStep, parsed)
          else if (parsed.content !== undefined) safeCallback(callbacks.onToken, parsed.content)
      }
    } catch (e) {
      console.warn('[Agent SSE] Parse error:', e)
    }
  }

  fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
      'Cache-Control': 'no-cache'
    },
    body: JSON.stringify(data),
    signal: controller.signal
  })
    .then(response => {
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let currentEventType = null
      let currentDataLines = []

      const processBuffer = () => {
        buffer = buffer.replace(/\r/g, '')
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          const trimmed = line.trim()
          if (trimmed === '') {
            if (currentEventType && currentDataLines.length > 0) {
              currentDataLines.forEach(d => handleEvent(currentEventType, d))
            }
            currentEventType = null
            currentDataLines = []
          } else if (trimmed.startsWith('event:')) {
            if (currentEventType && currentDataLines.length > 0) {
              currentDataLines.forEach(d => handleEvent(currentEventType, d))
            }
            currentEventType = trimmed.slice(6).trim()
            currentDataLines = []
          } else if (trimmed.startsWith('data:')) {
            currentDataLines.push(trimmed.slice(5))
          }
        }
      }

      const readChunk = () => {
        reader.read().then(({ done, value }) => {
          if (done) {
            if (buffer.trim()) { buffer += '\n'; processBuffer() }
            if (currentEventType && currentDataLines.length > 0) {
              currentDataLines.forEach(d => handleEvent(currentEventType, d))
            }
            if (!hasCompleted && !isAborted) {
              safeCallback(callbacks.onComplete, { sources: [], total_duration_ms: 0 })
            }
            return
          }
          buffer += decoder.decode(value, { stream: true })
          processBuffer()
          readChunk()
        }).catch(handleError)
      }
      readChunk()
    })
    .catch(handleError)

  return () => {
    isAborted = true
    controller.abort()
  }
}

/**
 * 流式查询知识库（SSE）
 * 支持新协议（step/token/done 事件）和旧协议（只有 data 字段）
 * @param {Object} data - { question: string, session_id?: string }
 * @param {Object} callbacks - 回调函数集合
 * @param {Function} callbacks.onStep - 步骤状态变化回调
 * @param {Function} callbacks.onToken - token 片段回调
 * @param {Function} callbacks.onComplete - 完成回调
 * @param {Function} callbacks.onError - 错误回调
 * @returns {Function} - 取消函数
 */
export function queryKnowledgeStream(data, callbacks) {
  // 开发环境直接调用后端 API，绕过 Vite 代理缓冲问题
  // 生产环境使用相对路径（通过 nginx 等代理）
  const isDev = import.meta.env.DEV
  const baseUrl = isDev ? 'http://127.0.0.1:8001' : (import.meta.env.VITE_API_BASE_URL || '')
  const url = `${baseUrl}/query/stream`

  console.log('[SSE DEBUG] URL:', url, 'isDev:', isDev)
  console.log('[SSE DEBUG] Request body:', JSON.stringify(data))

  const controller = new AbortController()
  let isAborted = false
  let hasCompleted = false

  const safeCallback = (fn, ...args) => {
    if (!isAborted && fn) {
      fn(...args)
    }
  }

  const handleError = (error) => {
    // 忽略用户主动取消的错误
    if (error.name === 'AbortError' || isAborted) {
      return
    }
    safeCallback(callbacks.onError, error)
  }

  /**
   * 处理单个 SSE 事件
   */
  const handleEvent = (eventType, dataStr) => {
    if (!dataStr || !dataStr.trim()) return

    try {
      const parsed = JSON.parse(dataStr)
      console.log('[SSE] Event:', eventType, parsed)

      switch (eventType) {
        case 'step':
          safeCallback(callbacks.onStep, parsed)
          break
        case 'token':
          safeCallback(callbacks.onToken, parsed.content)
          break
        case 'done':
          hasCompleted = true
          safeCallback(callbacks.onComplete, parsed)
          break
        default:
          // 兼容：根据内容推断类型
          if (parsed.sources) {
            hasCompleted = true
            safeCallback(callbacks.onComplete, parsed)
          } else if (parsed.step) {
            safeCallback(callbacks.onStep, parsed)
          } else if (parsed.content !== undefined) {
            safeCallback(callbacks.onToken, parsed.content)
          }
      }
    } catch (e) {
      console.warn('[SSE] Parse error:', e, 'data:', dataStr)
    }
  }

  fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
      'Cache-Control': 'no-cache'
    },
    body: JSON.stringify(data),
    signal: controller.signal
  })
    .then(response => {
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let currentEventType = null
      let currentDataLines = []

      /**
       * 按行处理 SSE 数据
       * SSE 格式：
       *   event: step
       *   data: {"step": "query_understanding", ...}
       *   (空行或下一 event: 行表示消息结束)
       */
      const processBuffer = () => {
        // 修复：先移除所有 \r，统一处理 \n 分隔符（SSE 标准允许 \r\n 或 \n）
        buffer = buffer.replace(/\r/g, '')
        // 按单换行分割
        const lines = buffer.split('\n')
        // 最后一个可能是不完整的行，保留在 buffer 中
        buffer = lines.pop() || ''

        for (const line of lines) {
          const trimmed = line.trim()

          if (trimmed === '') {
            // 空行：处理当前累积的事件
            if (currentEventType && currentDataLines.length > 0) {
              currentDataLines.forEach(d => handleEvent(currentEventType, d))
            }
            currentEventType = null
            currentDataLines = []
          } else if (trimmed.startsWith('event:')) {
            // 新事件开始：先处理之前累积的事件
            if (currentEventType && currentDataLines.length > 0) {
              currentDataLines.forEach(d => handleEvent(currentEventType, d))
            }
            currentEventType = trimmed.slice(6).trim()
            currentDataLines = []
          } else if (trimmed.startsWith('data:')) {
            currentDataLines.push(trimmed.slice(5))
          }
        }
      }

      const readChunk = () => {
        reader.read().then(({ done, value }) => {
          if (done) {
            // 处理 buffer 中剩余的内容
            if (buffer.trim()) {
              // 模拟添加最后的空行触发处理
              buffer += '\n'
              processBuffer()
            }
            // 处理最后可能未处理的事件
            if (currentEventType && currentDataLines.length > 0) {
              currentDataLines.forEach(d => handleEvent(currentEventType, d))
            }
            // 如果流结束但没有收到 done 事件
            if (!hasCompleted && !isAborted) {
              safeCallback(callbacks.onComplete, { sources: [], total_duration_ms: 0 })
            }
            return
          }

          // DEBUG: 打印原始接收的二进制数据
          const rawText = decoder.decode(value, { stream: true })
          console.log('[SSE DEBUG] Raw chunk received:', rawText.length, 'bytes')
          console.log('[SSE DEBUG] Raw content preview:', rawText.substring(0, 300))

          buffer += rawText
          processBuffer()
          readChunk()
        }).catch(handleError)
      }

      readChunk()
    })
    .catch(handleError)

  // 返回取消函数
  return () => {
    isAborted = true
    controller.abort()
  }
}