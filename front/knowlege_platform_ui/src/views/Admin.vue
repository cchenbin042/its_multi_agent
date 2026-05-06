<template>
  <div class="admin-container">
    <el-card class="admin-card">
      <template #header>
        <div class="card-header">
          <span>知识库文档管理</span>
          <el-input
            v-model="searchKeyword"
            placeholder="搜索标题..."
            clearable
            style="width: 300px"
            @clear="handleSearch"
            @keyup.enter="handleSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </div>
      </template>

      <el-table
        :data="documents"
        v-loading="loading"
        empty-text="暂无文档"
        stripe
      >
        <el-table-column label="标题" min-width="300" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-html="highlightedTitle(row.title)" />
            <el-tag v-if="isPendingReview(row.title)" type="danger" size="small" style="margin-left: 6px">
              待审核
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="path" label="路径" min-width="200" show-overflow-tooltip />
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="handlePreview(row)">
              <el-icon><View /></el-icon> 预览
            </el-button>
            <el-button size="small" type="danger" link @click="handleDelete(row)">
              <el-icon><Delete /></el-icon> 删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @size-change="fetchDocuments"
          @current-change="fetchDocuments"
        />
      </div>
    </el-card>

    <!-- 预览弹窗 -->
    <el-dialog v-model="previewVisible" :title="previewTitle" width="700px">
      <div class="preview-content" v-html="highlightedPreview" />
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { Search, View, Delete } from '@element-plus/icons-vue'
import { getDocuments, deleteDocument, getDocumentPreview, getFeedbackStats } from '@/api/knowledge'
import { ElMessage, ElMessageBox } from 'element-plus'

const documents = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const searchKeyword = ref('')
const loading = ref(false)

const previewVisible = ref(false)
const previewTitle = ref('')
const previewContent = ref('')

// 待审核文档标题集合
const pendingReviewTitles = ref(new Set())

const fetchPendingReviews = async () => {
  try {
    const fb = await getFeedbackStats(30)
    pendingReviewTitles.value = new Set(
      (fb.pending_review || []).map(p => p.title)
    )
  } catch (e) {
    console.error('Failed to fetch pending reviews:', e)
  }
}

const isPendingReview = (title) => {
  return pendingReviewTitles.value.has(title) || (
    // also check if any pending review title is contained in this title
    [...pendingReviewTitles.value].some(pt => title.includes(pt) || pt.includes(title))
  )
}

// 关键词高亮
const highlightText = (text) => {
  if (!text || !searchKeyword.value) return text
  const escaped = searchKeyword.value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const regex = new RegExp(`(${escaped})`, 'gi')
  return text.replace(regex, '<mark class="kw-highlight">$1</mark>')
}

const highlightedPreview = computed(() => {
  return highlightText(previewContent.value)
})

const highlightedTitle = (title) => {
  return highlightText(title)
}

const fetchDocuments = async () => {
  loading.value = true
  try {
    const offset = (currentPage.value - 1) * pageSize.value
    const res = await getDocuments({ offset, limit: pageSize.value, search: searchKeyword.value })
    documents.value = res.documents
    total.value = res.total
  } catch (e) {
    ElMessage.error('获取文档列表失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  currentPage.value = 1
  fetchDocuments()
}

const handlePreview = async (row) => {
  try {
    const res = await getDocumentPreview(row.title)
    previewTitle.value = row.title
    previewContent.value = res.content_preview
    previewVisible.value = true
  } catch (e) {
    ElMessage.error('获取文档预览失败')
  }
}

const handleDelete = (row) => {
  ElMessageBox.confirm(`确定删除文档「${row.title}」？删除后缓存将刷新。`, '确认删除', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning',
  }).then(async () => {
    try {
      await deleteDocument(row.title)
      ElMessage.success('文档已删除')
      fetchDocuments()
    } catch (e) {
      ElMessage.error('删除失败')
    }
  }).catch(() => {})
}

onMounted(() => {
  fetchDocuments()
  fetchPendingReviews()
})
</script>

<style lang="scss" scoped>
.admin-container {
  padding: 20px;
}

.admin-card {
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

.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.preview-content {
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 400px;
  overflow-y: auto;
  line-height: 1.6;
  color: #c9d1d9;
  background-color: #0d1117;
  padding: 16px;
  border-radius: 6px;

  :deep(mark.kw-highlight) {
    background-color: rgba(255, 213, 0, 0.35);
    color: #ffd54f;
    border-radius: 2px;
    padding: 0 2px;
  }
}
</style>
