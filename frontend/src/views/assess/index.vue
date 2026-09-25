<template>
  <section class="page" data-module="assess">
    <header class="page-head">
      <div>
        <h2>状态评估管理</h2>
        <p class="page-desc">维护评估记录，围绕评估周期、健康分值做登记、风险定级与复评；高风险设备请前往风险定位查看。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn primary" to="/assess/risk">风险定位</RouterLink>
        <button class="btn" type="button" @click="openCreate">登记评估记录</button>
        <button class="btn" type="button" @click="exportRows">导出状态评估清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>评估编号</span>
        <input v-model="keyword" placeholder="按评估编号检索" />
      </label>
      <label class="filter-item">
        <span>评估周期</span>
        <select v-model="periodFilter">
          <option value="">全部周期</option>
          <option v-for="p in periods" :key="p" :value="p">{{ p }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>评估状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>风险等级</span>
        <select v-model="riskFilter">
          <option value="">全部等级</option>
          <option v-for="r in riskLevels" :key="r" :value="r">{{ r }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <template v-if="column === '健康分值'">
              <span :class="{ 'cell-warn': row['健康分值'] == null || row['健康分值缺失原因'] }">
                {{ row['健康分值'] ?? '—' }}
              </span>
            </template>
            <template v-else-if="column === '风险等级'">
              <span v-if="row['风险等级']" class="risk-tag" :data-risk="riskKey(row['风险等级'])">{{ row['风险等级'] }}</span>
              <span v-else class="text-muted">—</span>
            </template>
            <template v-else-if="column === '评估状态'">
              {{ row['评估状态'] ?? row.status }}
            </template>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button v-if="row.status === '待评估'" class="link" type="button" @click="runAction('开始评估', row)">开始评估</button>
            <button v-if="row.status === '评估中'" class="link" type="button" @click="openGrade(row)">确认定级</button>
            <button
              v-if="row.status === '已定级' || row.status === '已复评'"
              class="link"
              type="button"
              @click="openReview(row)"
            >
              提交复评
            </button>
            <!-- 老的发起复评动作照旧：无表单、直达流转 -->
            <button
              v-if="row.status === '已定级'"
              class="link legacy"
              type="button"
              @click="runAction('发起复评', row)"
            >
              发起复评
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无符合条件的评估记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条状态评估记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 首次定级 / 提交复评 共用表单，校验不过逐字段标红 -->
    <div v-if="formVisible" class="modal-mask" @click.self="closeForm">
      <form class="modal" @submit.prevent="submitGradeForm">
        <h3 class="modal-title">{{ formMode === 'grade' ? '确认定级（首次定级）' : '提交复评' }}</h3>
        <p class="modal-sub">
          {{ formRow?.['评估对象'] }} · {{ formRow?.['评估周期'] }}
          <span v-if="formRow?.['复评轮次']" class="text-muted">（已复评 {{ formRow['复评轮次'] }} 轮）</span>
        </p>

        <label class="form-item">
          <span>健康分值<em>*</em></span>
          <input v-model="formValues['健康分值']" placeholder="0~100 的数值" />
          <small v-if="fieldErrors['健康分值']" class="field-error">{{ fieldErrors['健康分值'] }}</small>
        </label>

        <label class="form-item">
          <span>风险等级</span>
          <input :value="derivedRisk" type="text" readonly placeholder="按健康分值自动判定" />
          <small class="form-hint">风险等级由健康分值统一推导，不允许手工指定</small>
        </label>

        <label class="form-item">
          <span>评估结论<em>*</em></span>
          <textarea v-model="formValues['评估结论']" rows="3" :placeholder="conclusionPlaceholder"></textarea>
          <small v-if="fieldErrors['评估结论']" class="field-error">{{ fieldErrors['评估结论'] }}</small>
        </label>

        <label class="form-item">
          <span>评估人员<em>*</em></span>
          <input v-model="formValues['评估人员']" placeholder="复评人姓名" />
          <small v-if="fieldErrors['评估人员']" class="field-error">{{ fieldErrors['评估人员'] }}</small>
        </label>

        <p v-if="formErrorMessage" class="error-text form-error">{{ formErrorMessage }}</p>

        <div class="modal-actions">
          <button class="btn" type="button" @click="closeForm">取消</button>
          <button class="btn primary" type="submit" :disabled="submitting">
            {{ submitting ? '提交中…' : formMode === 'grade' ? '确认定级' : '提交复评' }}
          </button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type FormMode = 'grade' | 'review'

const ENDPOINT = '/api/assess'
const columns = ['评估编号', '评估对象', '评估周期', '健康分值', '风险等级', '评估人员', '评估结论', '评估状态']
const statuses = ['待评估', '评估中', '已定级', '已复评']
const riskLevels = ['重大风险', '较大风险', '一般风险', '低风险']

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const keyword = ref('')
const periodFilter = ref('')
const statusFilter = ref('')
const riskFilter = ref('')
const periods = ref<string[]>([])

// 首次定级与已复评分开统计，数字取自风险定位接口，保证各入口口径一致。
const statCards = ref([
  { label: '首次定级（本期）', value: '—' },
  { label: '已复评记录', value: '—' },
  { label: '高风险设备', value: '—' },
  { label: '健康分值均值', value: '—' },
  { label: '健康分值缺失', value: '—' },
])

const formVisible = ref(false)
const formMode = ref<FormMode>('grade')
const formRow = ref<Row | null>(null)
const formValues = ref<Record<string, string>>({})
const fieldErrors = ref<Record<string, string>>({})
const formErrorMessage = ref('')
const submitting = ref(false)

const derivedRisk = computed(() => {
  const score = Number(formValues.value['健康分值'])
  if (formValues.value['健康分值'] === '' || Number.isNaN(score) || score < 0 || score > 100) {
    return ''
  }
  if (score < 60) return '重大风险'
  if (score < 75) return '较大风险'
  if (score < 90) return '一般风险'
  return '低风险'
})

const conclusionPlaceholder = computed(() =>
  derivedRisk.value ? `以「${derivedRisk.value}，」开头，写明判定与处置意见` : '请先填写有效的健康分值',
)

function riskKey(level: unknown): string {
  const map: Record<string, string> = {
    重大风险: 'critical',
    较大风险: 'high',
    一般风险: 'medium',
    低风险: 'low',
  }
  return map[String(level ?? '')] ?? ''
}

function resetFilters() {
  keyword.value = ''
  periodFilter.value = ''
  statusFilter.value = ''
  riskFilter.value = ''
  void reload()
}

function exportRows() {
  const query = new URLSearchParams()
  if (periodFilter.value) query.set('period', periodFilter.value)
  window.open(`${ENDPOINT}/export?${query.toString()}`, '_blank')
}

function openCreate() {
  errorMessage.value = '评估记录登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload?.message ?? '状态评估动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '状态评估操作失败'
  }
}

function openGrade(row: Row) {
  formMode.value = 'grade'
  openForm(row)
}

function openReview(row: Row) {
  formMode.value = 'review'
  openForm(row)
}

function openForm(row: Row) {
  formRow.value = row
  formValues.value = {
    健康分值: row['健康分值'] == null ? '' : String(row['健康分值']),
    评估结论: '',
    评估人员: formMode.value === 'review' ? '' : String(row['评估人员'] ?? ''),
  }
  fieldErrors.value = {}
  formErrorMessage.value = ''
  formVisible.value = true
}

function closeForm() {
  if (submitting.value) return
  formVisible.value = false
  formRow.value = null
  fieldErrors.value = {}
  formErrorMessage.value = ''
}

async function submitGradeForm() {
  if (!formRow.value) return
  submitting.value = true
  fieldErrors.value = {}
  formErrorMessage.value = ''
  const path = formMode.value === 'grade' ? 'grade' : 'review'
  try {
    const response = await request(`${ENDPOINT}/${formRow.value.id}/${path}`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...formValues.value } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      fieldErrors.value = payload?.field_errors ?? {}
      formErrorMessage.value = payload?.message ?? '提交未通过校验'
      return
    }
    formVisible.value = false
    await reload()
  } catch (error) {
    formErrorMessage.value = error instanceof Error ? error.message : '提交失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value) query.set('keyword', keyword.value)
  if (periodFilter.value) query.set('period', periodFilter.value)
  if (statusFilter.value) query.set('status', statusFilter.value)
  if (riskFilter.value) query.set('risk', riskFilter.value)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('评估记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    await loadStats()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '状态评估列表读取失败'
  }
}

async function loadOptions() {
  try {
    const response = await request(`${ENDPOINT}/periods`)
    if (response.ok) {
      const payload = await response.json()
      periods.value = payload.items ?? []
    }
  } catch {
    periods.value = []
  }
}

async function loadStats() {
  try {
    const query = new URLSearchParams()
    if (periodFilter.value) query.set('period', periodFilter.value)
    const response = await request(`${ENDPOINT}/risk-board?${query.toString()}`)
    if (!response.ok) return
    const payload = await response.json()
    const stats = payload['统计'] ?? {}
    statCards.value = [
      { label: periodFilter.value ? `${periodFilter.value}首次定级` : '首次定级（跨周期）', value: stats['首次定级'] ?? 0 },
      { label: '已复评记录', value: stats['已复评'] ?? 0 },
      { label: '高风险设备', value: stats['高风险设备'] ?? 0 },
      { label: '健康分值均值', value: stats['健康分值均值'] ?? '—' },
      { label: '健康分值缺失', value: stats['健康分值缺失'] ?? 0 },
    ]
  } catch {
    // 统计卡片保持上一次的值，不打断列表操作
  }
}

onMounted(() => {
  void loadOptions()
  void reload()
})
</script>
