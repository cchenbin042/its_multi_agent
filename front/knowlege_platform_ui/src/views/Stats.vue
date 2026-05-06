<template>
  <div class="stats-container">
    <el-card class="stats-card">
      <template #header>
        <div class="card-header">
          <span>查询分析</span>
          <el-select v-model="days" @change="fetchStats" style="width: 120px">
            <el-option :value="1" label="今天" />
            <el-option :value="7" label="近7天" />
            <el-option :value="30" label="近30天" />
          </el-select>
        </div>
      </template>

      <div v-loading="loading">
        <!-- 概览卡片 -->
        <el-row :gutter="20" class="summary-row">
          <el-col :span="6">
            <div class="stat-card">
              <div class="stat-value">{{ stats.total_queries }}</div>
              <div class="stat-label">总查询数</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="stat-card">
              <div class="stat-value">{{ stats.avg_duration_ms }}ms</div>
              <div class="stat-label">平均耗时</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="stat-card">
              <div class="stat-value">{{ stats.avg_sources }}</div>
              <div class="stat-label">平均来源数</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="stat-card">
              <div class="stat-value">{{ stats.cache_hit_rate_pct }}%</div>
              <div class="stat-label">缓存命中率</div>
            </div>
          </el-col>
        </el-row>

        <el-row :gutter="20" class="summary-row" style="margin-top: 12px">
          <el-col :span="6">
            <div class="stat-card">
              <div class="stat-value">{{ stats.web_search_rate_pct }}%</div>
              <div class="stat-label">联网搜索触发率</div>
            </div>
          </el-col>
        </el-row>

        <!-- 每日趋势 -->
        <div v-if="dailyDates.length > 0" class="chart-section">
          <h4>每日查询趋势</h4>
          <div class="chart-wrapper">
            <div class="chart-bar" v-for="(item, idx) in stats.daily_counts" :key="idx">
              <div
                class="bar"
                :style="{ height: barHeight(item.count) + 'px' }"
                :title="`${item.date}: ${item.count} 次`"
              ></div>
              <div class="bar-label">{{ item.date.slice(5) }}</div>
              <div class="bar-count">{{ item.count }}</div>
            </div>
          </div>
        </div>

        <!-- 反馈分析 -->
        <div class="chart-section">
          <h4>用户反馈分析</h4>

          <el-row :gutter="20" class="summary-row">
            <el-col :span="6">
              <div class="stat-card">
                <div class="stat-value">{{ feedbackStats.total_feedback }}</div>
                <div class="stat-label">反馈总数</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="stat-card">
                <div class="stat-value" style="color: #3fb950">{{ feedbackStats.positive_count }}</div>
                <div class="stat-label">正面反馈</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="stat-card">
                <div class="stat-value" style="color: #f85149">{{ feedbackStats.negative_count }}</div>
                <div class="stat-label">负面反馈</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="stat-card">
                <div class="stat-value">{{ feedbackStats.positive_rate_pct }}%</div>
                <div class="stat-label">好评率</div>
              </div>
            </el-col>
          </el-row>

          <!-- 高负反馈文档 -->
          <div v-if="feedbackStats.top_negative_docs.length > 0" style="margin-top: 20px">
            <h4 style="margin-bottom: 8px">高负反馈文档 Top 10</h4>
            <el-table
              :data="feedbackStats.top_negative_docs"
              size="small"
              max-height="240"
              stripe
            >
              <el-table-column prop="title" label="文档标题" min-width="300" show-overflow-tooltip />
              <el-table-column prop="negative_count" label="负面反馈数" width="120" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.negative_count >= 5" type="danger" size="small">待审核</el-tag>
                  <span :style="{ color: row.negative_count >= 5 ? '#f85149' : '#c9d1d9' }">
                    {{ row.negative_count }}
                  </span>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <!-- 低分查询示例 -->
          <div v-if="feedbackStats.recent_negative_queries.length > 0" style="margin-top: 20px">
            <h4 style="margin-bottom: 8px">低分查询示例</h4>
            <el-table
              :data="feedbackStats.recent_negative_queries"
              size="small"
              max-height="240"
              stripe
            >
              <el-table-column prop="question" label="问题" min-width="250" show-overflow-tooltip />
              <el-table-column prop="timestamp" label="时间" width="160" />
            </el-table>
          </div>
        </div>

        <div v-if="!loading && stats.total_queries === 0" class="empty-state">
          暂无查询数据
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { getStats, getFeedbackStats } from '@/api/knowledge'

const stats = ref({
  total_queries: 0,
  avg_duration_ms: 0,
  avg_sources: 0,
  web_search_rate_pct: 0,
  cache_hit_rate_pct: 0,
  daily_counts: [],
})
const feedbackStats = ref({
  total_feedback: 0,
  positive_count: 0,
  negative_count: 0,
  positive_rate_pct: 0,
  top_negative_docs: [],
  recent_negative_queries: [],
  pending_review: [],
  daily_feedback: [],
})
const days = ref(7)
const loading = ref(false)

const dailyDates = computed(() => stats.value.daily_counts.map(i => i.date))

const fetchStats = async () => {
  loading.value = true
  try {
    const [s, fb] = await Promise.all([
      getStats(days.value),
      getFeedbackStats(days.value),
    ])
    stats.value = s
    feedbackStats.value = fb
  } catch (e) {
    console.error('Failed to fetch stats:', e)
  } finally {
    loading.value = false
  }
}

const maxCount = computed(() => {
  const cnts = stats.value.daily_counts.map(i => i.count)
  return cnts.length ? Math.max(...cnts, 1) : 1
})

const barHeight = (count) => {
  return Math.max(4, (count / maxCount.value) * 200)
}

onMounted(() => {
  fetchStats()
})
</script>

<style lang="scss" scoped>
.stats-container {
  padding: 20px;
}

.stats-card {
  background-color: #161b22;
  border: 1px solid #30363d;

  :deep(.el-card__header) {
    border-bottom: 1px solid #30363d;
  }
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: #c9d1d9;
  font-size: 16px;
  font-weight: 600;
}

.summary-row {
  margin-bottom: 20px;
}

.stat-card {
  background: #21262d;
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 16px;
  text-align: center;

  .stat-value {
    font-size: 28px;
    font-weight: 700;
    color: #58a6ff;
  }

  .stat-label {
    margin-top: 4px;
    font-size: 13px;
    color: #8b949e;
  }
}

.chart-section {
  margin-top: 24px;

  h4 {
    color: #c9d1d9;
    margin-bottom: 12px;
  }
}

.chart-wrapper {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  height: 260px;
  padding: 10px;
}

.chart-bar {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.bar {
  width: 100%;
  max-width: 40px;
  background: linear-gradient(180deg, #58a6ff, #3fb950);
  border-radius: 4px 4px 0 0;
  transition: height 0.3s;
}

.bar-label {
  font-size: 11px;
  color: #8b949e;
}

.bar-count {
  font-size: 12px;
  color: #c9d1d9;
  font-weight: 600;
}

.empty-state {
  text-align: center;
  color: #8b949e;
  padding: 40px;
}
</style>
