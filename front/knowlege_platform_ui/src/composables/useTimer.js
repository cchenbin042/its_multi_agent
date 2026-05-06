import { ref, computed, onUnmounted } from 'vue'

/**
 * 计时器 composable
 * 用于显示 RAG 检索过程的实时耗时
 */
export function useTimer() {
  const elapsed = ref(0) // 毫秒
  let startTime = 0
  let rafId = null

  const start = () => {
    startTime = performance.now()
    const tick = () => {
      elapsed.value = performance.now() - startTime
      rafId = requestAnimationFrame(tick)
    }
    tick()
  }

  const stop = () => {
    if (rafId) {
      cancelAnimationFrame(rafId)
      rafId = null
    }
  }

  const reset = () => {
    stop()
    elapsed.value = 0
  }

  const formatted = computed(() => {
    const seconds = elapsed.value / 1000
    return seconds.toFixed(1) + 's'
  })

  onUnmounted(stop)

  return { elapsed, formatted, start, stop, reset }
}

/**
 * 格式化毫秒为可读字符串
 * @param {number} ms 毫秒数
 * @returns {string} 格式化后的时间字符串
 */
export function formatDuration(ms) {
  if (!ms || ms <= 0) return ''
  const seconds = ms / 1000
  if (seconds < 1) {
    return `${Math.round(ms)}ms`
  }
  return `${seconds.toFixed(1)}s`
}