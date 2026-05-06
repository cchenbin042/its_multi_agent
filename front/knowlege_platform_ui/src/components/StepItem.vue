<template>
  <div class="step-item" :class="step.status">
    <!-- 状态图标 -->
    <div class="step-icon">
      <!-- Pending: 灰色空心圆 -->
      <span v-if="step.status === 'pending'" class="icon-pending">
        <svg viewBox="0 0 16 16" width="16" height="16">
          <circle cx="8" cy="8" r="7" fill="none" stroke="currentColor" stroke-width="1.5" />
        </svg>
      </span>
      <!-- Running: 旋转圆环 -->
      <span v-else-if="step.status === 'running'" class="icon-running">
        <svg class="spinner" viewBox="0 0 24 24" width="16" height="16">
          <circle cx="12" cy="12" r="10" stroke="#30363d" stroke-width="2" fill="none" />
          <path d="M12 2 a10 10 0 0 1 10 10" stroke="#58a6ff" stroke-width="2" stroke-linecap="round" fill="none" />
        </svg>
      </span>
      <!-- Completed: 绿色对勾 -->
      <span v-else-if="step.status === 'completed'" class="icon-completed">
        <svg viewBox="0 0 16 16" width="16" height="16">
          <path d="M3 8l3 3 7-7" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </span>
      <!-- Error: 红色叉号 -->
      <span v-else class="icon-error">
        <svg viewBox="0 0 16 16" width="16" height="16">
          <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
        </svg>
      </span>
    </div>

    <!-- 步骤标签 -->
    <div class="step-label" @click="toggleCollapse">
      <span class="label-text">
        {{ step.label }}
        <!-- Running 状态脉冲省略号 -->
        <span v-if="step.status === 'running'" class="pulse-dots">
          <span>.</span><span>.</span><span>.</span>
        </span>
      </span>

      <!-- 耗时标签（仅完成态显示） -->
      <span v-if="step.status === 'completed' && step.durationMs" class="duration-badge">
        {{ formatDuration(step.durationMs) }}
      </span>

      <!-- 折叠箭头（有详情时显示） -->
      <span v-if="hasDetail" class="collapse-arrow" :class="{ expanded: !step.collapsed }">
        <svg viewBox="0 0 16 16" width="14" height="14">
          <path d="M6 4l4 4-4 4" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </span>
    </div>

    <!-- 折叠详情区 -->
    <Transition name="detail-expand">
      <div v-if="hasDetail && !step.collapsed" class="step-detail">
        <!-- 查询理解：展示扩展后的查询 -->
        <template v-if="step.key === 'query_understanding'">
          <div v-for="q in step.detail.expanded_queries" :key="q" class="detail-tag">
            {{ q }}
          </div>
        </template>

        <!-- 知识检索：展示候选数量 -->
        <template v-else-if="step.key === 'knowledge_retrieval'">
          <span v-if="step.detail.candidate_count !== undefined" class="detail-text">
            召回 {{ step.detail.candidate_count }} 篇候选文档
          </span>
        </template>

        <!-- 精排筛选：展示最终数量和 Top 标题 -->
        <template v-else-if="step.key === 'reranking'">
          <span v-if="step.detail.final_count !== undefined" class="detail-text">
            筛选出 {{ step.detail.final_count }} 篇相关文档
          </span>
          <div v-for="(t, idx) in step.detail.top_titles" :key="idx" class="detail-tag">
            {{ t }}
          </div>
        </template>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatDuration } from '@/composables/useTimer'

const props = defineProps({
  step: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['toggle'])

const hasDetail = computed(() => {
  const detail = props.step.detail
  if (!detail) return false

  if (props.step.key === 'query_understanding' && detail.expanded_queries?.length) {
    return true
  }
  if (props.step.key === 'knowledge_retrieval' && detail.candidate_count !== undefined) {
    return true
  }
  if (props.step.key === 'reranking' && (detail.final_count !== undefined || detail.top_titles?.length)) {
    return true
  }
  return false
})

const toggleCollapse = () => {
  if (hasDetail.value) {
    emit('toggle', props.step.key)
  }
}
</script>

<style lang="scss" scoped>
.step-item {
  padding: 6px 0;
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 8px;

  &.pending {
    .step-label {
      color: #484f58;
    }
  }

  &.running {
    .step-label {
      color: #c9d1d9;
    }
  }

  &.completed {
    .step-label {
      color: #8b949e;
    }
  }

  &.error {
    .step-label {
      color: #f85149;
    }
  }
}

.step-icon {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.icon-pending {
  color: #484f58;
}

.icon-running .spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.icon-completed {
  color: #3fb950;
  display: inline-flex;
  animation: check-pop 0.3s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
}

@keyframes check-pop {
  0% {
    transform: scale(0);
    opacity: 0;
  }
  60% {
    transform: scale(1.2);
    opacity: 1;
  }
  100% {
    transform: scale(1);
    opacity: 1;
  }
}

.icon-error {
  color: #f85149;
}

.step-label {
  display: flex;
  align-items: center;
  font-size: 13px;
  cursor: pointer;
  user-select: none;

  .label-text {
    display: flex;
    align-items: center;
  }
}

.pulse-dots {
  display: inline-flex;
  margin-left: 2px;

  span {
    animation: dot-fade 1.4s infinite ease-in-out both;
    opacity: 0;

    &:nth-child(1) {
      animation-delay: 0s;
    }
    &:nth-child(2) {
      animation-delay: 0.2s;
    }
    &:nth-child(3) {
      animation-delay: 0.4s;
    }
  }
}

@keyframes dot-fade {
  0%,
  80%,
  100% {
    opacity: 0;
  }
  40% {
    opacity: 1;
  }
}

.duration-badge {
  font-size: 12px;
  color: #8b949e;
  margin-left: 8px;
  animation: fade-in 0.3s ease forwards;
  font-family: 'SF Mono', 'Fira Code', monospace;
}

@keyframes fade-in {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.collapse-arrow {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-left: 4px;
  color: #8b949e;
  transition: transform 0.2s ease;

  &.expanded {
    transform: rotate(90deg);
  }
}

.step-detail {
  width: 100%;
  padding-left: 28px;
  font-size: 12px;
  color: #8b949e;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.detail-tag {
  background-color: rgba(56, 139, 253, 0.1);
  border: 1px solid rgba(56, 139, 253, 0.2);
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 12px;
  color: #58a6ff;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-text {
  color: #8b949e;
}

/* 详情区展开/折叠动画 */
.detail-expand-enter-active,
.detail-expand-leave-active {
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  overflow: hidden;
}

.detail-expand-enter-from,
.detail-expand-leave-to {
  max-height: 0;
  opacity: 0;
  margin-top: 0;
}

.detail-expand-enter-to,
.detail-expand-leave-from {
  max-height: 200px;
  opacity: 1;
  margin-top: 8px;
}
</style>