<template>
  <div class="retrieval-steps">
    <!-- 折叠头 -->
    <div class="steps-header" @click="toggleAll">
      <span class="header-icon">
        <svg v-if="allCompleted" viewBox="0 0 16 16" width="14" height="14">
          <path d="M3 8l3 3 7-7" stroke="#3fb950" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        <svg v-else viewBox="0 0 16 16" width="14" height="14">
          <path d="M8 1v2M8 13v2M1 8h2M13 8h2" stroke="#58a6ff" stroke-width="1.5" stroke-linecap="round" />
          <circle cx="8" cy="8" r="3" stroke="#58a6ff" stroke-width="1.5" fill="none" />
        </svg>
      </span>
      <span class="header-text">
        {{ allCompleted ? '检索完成' : '处理中...' }}
      </span>
      <span v-if="allCompleted && totalDuration" class="header-duration">
        {{ formatDuration(totalDuration) }}
      </span>
      <span v-if="loading" class="timer-badge">
        <span class="timer-dot"></span>
        {{ timer.formatted.value }}
      </span>
      <span class="collapse-arrow" :class="{ expanded: !collapsed }">
        <svg viewBox="0 0 16 16" width="14" height="14">
          <path d="M6 4l4 4-4 4" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </span>
    </div>

    <!-- 步骤列表 -->
    <Transition name="steps-collapse">
      <div v-show="!collapsed" class="steps-list">
        <StepItem
          v-for="step in steps"
          :key="step.key"
          :step="step"
          @toggle="handleToggle"
        />
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import StepItem from './StepItem.vue'
import { formatDuration } from '@/composables/useTimer'

const props = defineProps({
  steps: {
    type: Array,
    required: true
  },
  totalDuration: {
    type: Number,
    default: 0
  },
  loading: {
    type: Boolean,
    default: false
  },
  timer: {
    type: Object,
    default: () => ({ formatted: { value: '0.0s' } })
  }
})

const emit = defineEmits(['toggle-step'])

const collapsed = defineModel('collapsed', { default: false })

const allCompleted = computed(() => {
  return props.steps.every(step => step.status === 'completed')
})

const toggleAll = () => {
  collapsed.value = !collapsed.value
}

const handleToggle = (stepKey) => {
  emit('toggle-step', stepKey)
}
</script>

<style lang="scss" scoped>
.retrieval-steps {
  margin: 12px 0 16px;
  padding: 0;
}

.steps-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  border-radius: 6px;
  font-size: 13px;
  color: #8b949e;
  transition: background-color 0.15s ease;

  &:hover {
    background-color: rgba(255, 255, 255, 0.04);
  }
}

.header-icon {
  display: flex;
  align-items: center;
  justify-content: center;
}

.header-text {
  flex: 1;
}

.header-duration {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 12px;
  color: #3fb950;
}

.timer-badge {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 13px;
  color: #58a6ff;
  display: flex;
  align-items: center;
  gap: 6px;
}

.timer-dot {
  width: 6px;
  height: 6px;
  background-color: #58a6ff;
  border-radius: 50%;
  animation: timer-pulse 1.5s ease-in-out infinite;
}

@keyframes timer-pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.4;
    transform: scale(0.8);
  }
}

.collapse-arrow {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #8b949e;
  transition: transform 0.2s ease;

  &.expanded {
    transform: rotate(90deg);
  }
}

.steps-list {
  padding-left: 12px;
  border-left: 2px solid #21262d;
  margin-left: 18px;
}

/* 步骤区整体折叠动画 */
.steps-collapse-enter-active,
.steps-collapse-leave-active {
  transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
  overflow: hidden;
}

.steps-collapse-enter-from,
.steps-collapse-leave-to {
  max-height: 0;
  opacity: 0;
}

.steps-collapse-enter-to,
.steps-collapse-leave-from {
  max-height: 500px;
  opacity: 1;
}
</style>