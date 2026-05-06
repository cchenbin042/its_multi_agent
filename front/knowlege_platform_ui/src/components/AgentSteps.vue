<template>
  <div class="agent-steps">
    <div class="steps-header">
      <span class="header-icon">
        <svg v-if="allCompleted" viewBox="0 0 16 16" width="14" height="14">
          <path d="M3 8l3 3 7-7" stroke="#3fb950" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        <svg v-else viewBox="0 0 16 16" width="14" height="14">
          <circle cx="8" cy="8" r="3" stroke="#f0883e" stroke-width="1.5" fill="none" />
          <path d="M8 4v5M8 10.5v.5" stroke="#f0883e" stroke-width="1.5" stroke-linecap="round" />
        </svg>
      </span>
      <span class="header-text">
        {{ allCompleted ? '深度推理完成' : '深度推理中...' }}
      </span>
      <span v-if="totalDuration" class="header-duration">
        {{ formatDuration(totalDuration) }}
      </span>
    </div>

    <div class="rounds-list">
      <div
        v-for="(round, idx) in rounds"
        :key="idx"
        class="round-item"
        :class="{ running: round.status === 'running' }"
      >
        <div class="round-header">
          <span class="round-badge">第 {{ round.round }} 轮</span>
          <span v-if="round.status === 'running'" class="round-status running">
            <span class="spinner"></span> 搜索中
          </span>
          <span v-else class="round-status completed">已完成</span>
        </div>

        <!-- 推理过程（可折叠） -->
        <div v-if="round.reasoning" class="reasoning-section">
          <div class="reasoning-toggle" @click="round._reasoningOpen = !round._reasoningOpen">
            <el-icon :size="14">
              <component :is="round._reasoningOpen ? 'CaretBottom' : 'CaretRight'" />
            </el-icon>
            <span>思考过程</span>
          </div>
          <div v-show="round._reasoningOpen" class="reasoning-content">
            {{ round.reasoning }}
          </div>
        </div>

        <div v-if="round.tool_calls?.length" class="tool-calls">
          <div v-for="(tc, tci) in round.tool_calls" :key="tci" class="tool-call">
            <el-icon :size="14"><Search /></el-icon>
            <span class="tool-name">{{ tc.tool }}</span>
            <span class="tool-query">"{{ tc.query }}"</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Search, CaretBottom, CaretRight } from '@element-plus/icons-vue'
import { formatDuration } from '@/composables/useTimer'

const props = defineProps({
  rounds: {
    type: Array,
    required: true
  },
  totalDuration: {
    type: Number,
    default: 0
  }
})

const allCompleted = computed(() => {
  return props.rounds.length > 0 && props.rounds.every(r => r.status === 'completed')
})
</script>

<style lang="scss" scoped>
.agent-steps {
  margin: 12px 0 16px;
}

.steps-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
  color: #8b949e;

  .header-icon {
    display: flex;
    align-items: center;
  }

  .header-text {
    flex: 1;
  }

  .header-duration {
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 12px;
    color: #3fb950;
  }
}

.rounds-list {
  padding-left: 12px;
  border-left: 2px solid #21262d;
  margin-left: 18px;
  margin-top: 8px;
}

.round-item {
  padding: 8px 12px;
  border-radius: 6px;
  margin-bottom: 6px;
  background: #1a1f29;
  border: 1px solid #21262d;
  transition: border-color 0.2s;

  &.running {
    border-color: #f0883e;
  }
}

.round-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.round-badge {
  font-size: 12px;
  font-weight: 600;
  color: #58a6ff;
  background: rgba(88, 166, 255, 0.1);
  padding: 2px 8px;
  border-radius: 4px;
}

.round-status {
  font-size: 12px;

  &.running {
    color: #f0883e;
    display: flex;
    align-items: center;
    gap: 4px;
  }

  &.completed {
    color: #3fb950;
  }
}

.spinner {
  width: 10px;
  height: 10px;
  border: 2px solid rgba(240, 136, 62, 0.3);
  border-top-color: #f0883e;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.reasoning-section {
  margin-bottom: 6px;
}

.reasoning-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #8b949e;
  cursor: pointer;
  padding: 2px 0;
  user-select: none;

  &:hover {
    color: #c9d1d9;
  }

  .el-icon {
    color: #f0883e;
  }
}

.reasoning-content {
  margin-top: 4px;
  padding: 8px;
  background: #161b22;
  border-radius: 4px;
  border-left: 2px solid #f0883e;
  font-size: 12px;
  color: #c9d1d9;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

.tool-calls {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tool-call {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  background: #161b22;
  border-radius: 4px;
  font-size: 12px;
  color: #c9d1d9;

  .el-icon {
    color: #3fb950;
    flex-shrink: 0;
  }

  .tool-name {
    font-family: 'SF Mono', 'Fira Code', monospace;
    color: #d2a8ff;
    flex-shrink: 0;
  }

  .tool-query {
    color: #8b949e;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}
</style>
