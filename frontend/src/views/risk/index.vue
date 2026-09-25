<template>
  <section class="page" data-module="risk">
    <header class="page-head">
      <div>
        <h2>风险定位</h2>
        <p class="page-desc">按健康分值与风险等级把高风险设备排在前面，按评估周期过滤已出复评结论的对象；首次定级与已复评分开统计，分值缺失的对象单独说明原因。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/assess">返回状态评估列表</RouterLink>
      </div>
    </header>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>评估周期</span>
        <select v-model="selectedPeriod">
          <option value="">全部周期（跨周期同设备只保留最新周期）</option>
          <option v-for="period in periods" :key="period" :value="period">{{ period }}</option>
        </select>
      </label>
      <button class="btn primary" type="submit">刷新定位结果</button>
    </form>

    <div v-if="overview?.cross_deduped" class="hint-bar">
      当前为跨周期定位：同一台设备在多个周期有记录时，只展示其最新周期的一条，不会重复出现。
    </div>

    <div v-if="errorMessage" class="error-banner">{{ errorMessage }}</div>

    <h3 class="block-title">首次定级结果（{{ firstStats['合计'] ?? 0 }} 台）</h3>
    <div class="stat-row">
      <article v-for="level in levelOrder" :key="level" class="stat-card" :class="cardClass(level)">
        <span class="stat-label">{{ level }}（首次定级）</span>
        <strong class="stat-value">{{ firstStats[level] ?? 0 }}</strong>
      </article>
    </div>

    <h3 class="block-title">已复评记录（{{ reviewedStats['合计'] ?? 0 }} 台）</h3>
    <div class="stat-row">
      <article v-for="level in levelOrder" :key="level" class="stat-card" :class="cardClass(level)">
        <span class="stat-label">{{ level }}（已复评）</span>
        <strong class="stat-value">{{ reviewedStats[level] ?? 0 }}</strong>
      </article>
    </div>

    <div v-if="consistency.mismatch_count" class="warn-bar">
      口径巡检发现 {{ consistency.mismatch_count }} 条记录的风险等级/评估结论与健康分值对不上，已在下表用「口径不符」标出。
    </div>
    <div v-else class="ok-bar">口径巡检通过：各记录风险等级与评估结论均与健康分值一致。</div>

    <h3 class="block-title">风险设备排序（高风险在前，同等级按健康分值升序）</h3>
    <table class="data-table">
      <thead>
        <tr>
          <th>排序</th>
          <th>评估编号</th>
          <th>评估对象</th>
          <th>评估周期</th>
          <th>健康分值</th>
          <th>风险等级</th>
          <th>评估结论</th>
          <th>定级情况</th>
          <th>口径核对</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(item, index) in riskItems" :key="String(item.id)">
          <td>{{ index + 1 }}</td>
          <td>{{ item['评估编号'] ?? '—' }}</td>
          <td>{{ item['评估对象'] ?? '—' }}</td>
          <td>{{ item['评估周期'] ?? '—' }}</td>
          <td><strong :class="scoreClass(item['健康分值'])">{{ item['健康分值'] }}</strong></td>
          <td><span class="risk-tag" :class="tagClass(item['风险等级'])">{{ item['风险等级'] }}</span></td>
          <td>{{ item['评估结论'] || '—' }}</td>
          <td>{{ item['首次定级'] ? '首次定级' : item['评估状态'] }}</td>
          <td>
            <span v-if="item['口径一致']" class="ok-text">一致</span>
            <div v-else class="mismatch-cell">
              <span class="error-text">口径不符</span>
              <ul class="issue-list">
                <li v-for="(issue, i) in item['差异说明']" :key="i">{{ issue }}</li>
              </ul>
            </div>
          </td>
          <td class="row-actions">
            <button
              v-if="item['首次定级']"
              class="link"
              type="button"
              @click="openReview(item)"
            >
              提交复评
            </button>
            <span v-else class="muted-text">已复评，不可重复提交</span>
          </td>
        </tr>
        <tr v-if="!riskItems.length">
          <td colspan="10" class="empty-state">当前周期没有待定位风险的设备（已复评对象已过滤）</td>
        </tr>
      </tbody>
    </table>

    <h3 class="block-title">健康分值缺失/异常对象（{{ missingScore.length }} 台，需先补录分值）</h3>
    <table class="data-table">
      <thead>
        <tr>
          <th>评估编号</th>
          <th>评估对象</th>
          <th>评估周期</th>
          <th>填报分值</th>
          <th>评估状态</th>
          <th>缺失原因</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in missingScore" :key="`missing-${String(item.id)}`">
          <td>{{ item['评估编号'] ?? '—' }}</td>
          <td>{{ item['评估对象'] ?? '—' }}</td>
          <td>{{ item['评估周期'] ?? '—' }}</td>
          <td>{{ item['健康分值'] === '' || item['健康分值'] === null ? '（空）' : item['健康分值'] }}</td>
          <td>{{ item['评估状态'] }}</td>
          <td class="error-text">{{ item['缺失原因'] }}</td>
        </tr>
        <tr v-if="!missingScore.length">
          <td colspan="6" class="empty-state">没有分值缺失或异常的对象</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>本次定位到 {{ overview?.located_total ?? 0 }} 台风险设备（已排除已复评对象）</span>
    </footer>

    <div v-if="reviewOpen" class="modal-mask" @click.self="closeReview">
      <div class="modal-card">
        <h3>提交复评结论 · {{ reviewForm['评估对象'] }}</h3>
        <p class="modal-sub">{{ reviewForm['评估编号'] }} · 当前分值 {{ reviewForm._oldScore }}（{{ reviewForm._oldLevel }}）</p>

        <form class="review-form" @submit.prevent="submitReview">
          <label class="form-item">
            <span>复评健康分值 <em>*</em></span>
            <input v-model="reviewForm['健康分值']" placeholder="请输入 0~100 的数值" />
            <small v-if="fieldErrors['健康分值']" class="field-error">{{ fieldErrors['健康分值'] }}</small>
          </label>
          <label class="form-item">
            <span>复评评估结论 <em>*</em></span>
            <select v-model="reviewForm['评估结论']">
              <option value="" disabled>请选择评估结论</option>
              <option v-for="level in levelOrder" :key="level" :value="RISK_CONCLUSIONS[level]">
                {{ RISK_CONCLUSIONS[level] }}
              </option>
            </select>
            <small v-if="fieldErrors['评估结论']" class="field-error">{{ fieldErrors['评估结论'] }}</small>
          </label>
          <label class="form-item">
            <span>复评评估人员 <em>*</em></span>
            <input v-model="reviewForm['评估人员']" placeholder="请填写评估人员" />
            <small v-if="fieldErrors['评估人员']" class="field-error">{{ fieldErrors['评估人员'] }}</small>
          </label>

          <p v-if="previewLevel" class="preview-hint" :class="tagClass(previewLevel)">
            按分值 {{ reviewScore }} 预判为{{ previewLevel }}，提交时会再次校验结论是否与之匹配。
          </p>

          <p v-if="reviewMessage" :class="reviewOk ? 'ok-text' : 'error-text'">{{ reviewMessage }}</p>

          <div class="modal-actions">
            <button class="btn" type="button" @click="closeReview">取消</button>
            <button class="btn primary" type="submit" :disabled="submitting">
              {{ submitting ? '提交中…' : '确认提交复评' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { RISK_CONCLUSIONS, RISK_LEVELS, parseScore, riskLevelOf } from '@/views/risk/riskRules'

interface RiskItem {
  id: number
  评估编号: string
  评估对象: string
  评估周期: string
  健康分值: number | null
  风险等级: string | null
  评估结论: string
  评估状态: string
  首次定级: boolean
  口径一致: boolean
  差异说明: string[]
}

interface MissingItem {
  id: number
  评估编号: string
  评估对象: string
  评估周期: string
  健康分值: string | number | null
  评估状态: string
  缺失原因: string
}

interface Overview {
  periods: string[]
  selected_period: string
  cross_deduped: boolean
  located_total: number
  first_level_stats: Record<string, number>
  reviewed_stats: Record<string, number>
  risk_items: RiskItem[]
  missing_score: MissingItem[]
  consistency: { checked: number; mismatch_count: number }
}

const ENDPOINT = '/api/assess'
const levelOrder = RISK_LEVELS

const periods = ref<string[]>([])
const selectedPeriod = ref('')
const overview = ref<Overview | null>(null)
const errorMessage = ref('')

const riskItems = computed<RiskItem[]>(() => overview.value?.risk_items ?? [])
const missingScore = computed<MissingItem[]>(() => overview.value?.missing_score ?? [])
const firstStats = computed(() => overview.value?.first_level_stats ?? {})
const reviewedStats = computed(() => overview.value?.reviewed_stats ?? {})
const consistency = computed(() => overview.value?.consistency ?? { checked: 0, mismatch_count: 0 })

const reviewOpen = ref(false)
const submitting = ref(false)
const reviewMessage = ref('')
const reviewOk = ref(false)
const fieldErrors = ref<Record<string, string>>({})
const reviewForm = ref<Record<string, string | number>>({})

const reviewScore = computed(() => parseScore(reviewForm.value['健康分值']))
const previewLevel = computed(() => (reviewScore.value === null ? '' : riskLevelOf(reviewScore.value)))

function cardClass(level: string): string {
  return { 高风险: 'card-high', 中风险: 'card-mid', 低风险: 'card-low' }[level] ?? ''
}

function tagClass(level: string | null): string {
  return { 高风险: 'tag-high', 中风险: 'tag-mid', 低风险: 'tag-low' }[level ?? ''] ?? ''
}

function scoreClass(score: number | null): string {
  const parsed = parseScore(score)
  if (parsed === null) return ''
  return tagClass(riskLevelOf(parsed))
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (selectedPeriod.value) query.set('period', selectedPeriod.value)
  try {
    const response = await request(`${ENDPOINT}/risk/overview?${query.toString()}`)
    if (!response.ok) throw new Error('风险定位数据读取失败')
    const payload = (await response.json()) as Overview
    overview.value = payload
    periods.value = payload.periods ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '风险定位数据读取失败'
  }
}

function openReview(item: RiskItem) {
  reviewOpen.value = true
  reviewMessage.value = ''
  fieldErrors.value = {}
  reviewForm.value = {
    id: item.id,
    评估对象: item['评估对象'],
    评估编号: item['评估编号'],
    _oldScore: item['健康分值'] ?? '—',
    _oldLevel: item['风险等级'] ?? '未定级',
    健康分值: '',
    评估结论: '',
    评估人员: '',
  }
}

function closeReview() {
  reviewOpen.value = false
  reviewMessage.value = ''
  fieldErrors.value = {}
}

function validateLocally(): boolean {
  const errors: Record<string, string> = {}
  const score = parseScore(reviewForm.value['健康分值'])
  if (reviewForm.value['健康分值'] === '' || reviewForm.value['健康分值'] === null) {
    errors['健康分值'] = '请填写复评健康分值'
  } else if (score === null) {
    errors['健康分值'] = '健康分值需为 0~100 的数值'
  }
  if (!String(reviewForm.value['评估结论'] ?? '').trim()) errors['评估结论'] = '请选择复评评估结论'
  if (!String(reviewForm.value['评估人员'] ?? '').trim()) errors['评估人员'] = '请填写复评评估人员'
  if (score !== null && reviewForm.value['评估结论']) {
    const expected = RISK_CONCLUSIONS[riskLevelOf(score)]
    if (reviewForm.value['评估结论'] !== expected) {
      errors['评估结论'] = `评估结论与分值口径不一致：分值对应${riskLevelOf(score)}，请选择「${expected}」`
    }
  }
  fieldErrors.value = errors
  return Object.keys(errors).length === 0
}

async function submitReview() {
  reviewMessage.value = ''
  if (!validateLocally()) {
    reviewOk.value = false
    reviewMessage.value = '复评提交校验未通过，请按字段提示修正后再提交'
    return
  }
  submitting.value = true
  try {
    const id = reviewForm.value.id
    const response = await request(`${ENDPOINT}/${id}/review`, {
      method: 'POST',
      body: JSON.stringify({
        values: {
          健康分值: reviewForm.value['健康分值'],
          评估结论: reviewForm.value['评估结论'],
          评估人员: reviewForm.value['评估人员'],
        },
      }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      reviewOk.value = false
      fieldErrors.value = payload.entry?.errors ?? {}
      reviewMessage.value = payload.message ?? '复评提交未生效，请稍后重试'
      return
    }
    reviewOk.value = true
    reviewMessage.value = payload.message ?? '复评结论已提交'
    await reload()
    setTimeout(closeReview, 800)
  } catch (error) {
    reviewOk.value = false
    reviewMessage.value = error instanceof Error ? error.message : '复评提交失败'
  } finally {
    submitting.value = false
  }
}

onMounted(reload)
</script>

<style scoped>
.block-title { font-size: 14px; margin: 16px 0 8px; }
.card-high { border-left: 4px solid #d92d20; }
.card-mid { border-left: 4px solid #f79009; }
.card-low { border-left: 4px solid #12b76a; }
.tag-high { color: #b42318; }
.tag-mid { color: #b54708; }
.tag-low { color: #027a48; }
.risk-tag { font-weight: 600; }
.hint-bar, .warn-bar, .ok-bar { font-size: 12px; padding: 8px 10px; border-radius: 6px; margin-bottom: 12px; }
.hint-bar { background: #eff8ff; border: 1px solid #b2ddff; color: #175cd3; }
.warn-bar { background: #fffaeb; border: 1px solid #fedf89; color: #b54708; }
.ok-bar { background: #ecfdf3; border: 1px solid #abefc6; color: #027a48; }
.error-banner { background: #fef3f2; border: 1px solid #fda29b; color: #b42318; font-size: 12px; padding: 8px 10px; border-radius: 6px; margin-bottom: 12px; }
.ok-text { color: #027a48; }
.muted-text { color: var(--muted); font-size: 12px; }
.mismatch-cell .issue-list { margin: 4px 0 0; padding-left: 16px; color: var(--muted); font-size: 12px; }
.modal-mask { position: fixed; inset: 0; background: rgba(16, 24, 40, 0.45); display: flex; align-items: center; justify-content: center; z-index: 20; }
.modal-card { background: #fff; border-radius: 10px; padding: 20px 24px; width: 460px; max-width: calc(100vw - 32px); }
.modal-card h3 { margin: 0; font-size: 15px; }
.modal-sub { color: var(--muted); font-size: 12px; margin: 4px 0 14px; }
.review-form { display: flex; flex-direction: column; gap: 12px; }
.form-item { display: flex; flex-direction: column; gap: 4px; font-size: 13px; }
.form-item input, .form-item select { padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; font: inherit; }
.form-item em { color: #d92d20; font-style: normal; }
.field-error { color: #b42318; font-size: 12px; }
.preview-hint { font-size: 12px; margin: 0; padding: 6px 8px; border-radius: 6px; background: #f9fafb; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 4px; }
select { padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; background: #fff; }
</style>
