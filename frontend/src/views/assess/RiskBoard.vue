<template>
  <section class="page" data-module="assess-risk">
    <header class="page-head">
      <div>
        <h2>风险定位</h2>
        <p class="page-desc">
          按健康分值与风险等级把高风险设备排在最前；只保留各设备最新评估周期的结论，未出结论的对象不参与定位。
        </p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/assess">返回状态评估</RouterLink>
      </div>
    </header>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>评估周期</span>
        <select v-model="period">
          <option value="">跨周期（同设备只取最新结论）</option>
          <option v-for="p in periods" :key="p" :value="p">{{ p }}</option>
        </select>
      </label>
      <button class="btn primary" type="submit">定位风险</button>
    </form>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card" :class="{ 'stat-alert': item.alert }">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <h3 class="block-title">风险设备排序<span class="block-hint">高风险在前，同等级按健康分值升序</span></h3>
    <table class="data-table">
      <thead>
        <tr>
          <th style="width: 48px">序</th>
          <th>评估对象</th>
          <th>评估周期</th>
          <th>健康分值</th>
          <th>风险等级</th>
          <th>评估状态</th>
          <th>评估人员</th>
          <th>评估结论</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, index) in ranked" :key="String(row.id)" :class="{ 'row-critical': row['风险等级'] === '重大风险' }">
          <td>{{ index + 1 }}</td>
          <td>{{ row['评估对象'] }}</td>
          <td>{{ row['评估周期'] }}</td>
          <td><strong>{{ row['健康分值'] }}</strong></td>
          <td><span class="risk-tag" :data-risk="riskKey(row['风险等级'])">{{ row['风险等级'] }}</span></td>
          <td>
            {{ row.status }}
            <span v-if="row['复评轮次']" class="text-muted">（复评 {{ row['复评轮次'] }} 轮）</span>
          </td>
          <td>{{ row['评估人员'] }}</td>
          <td>{{ row['评估结论'] }}</td>
        </tr>
        <tr v-if="!ranked.length">
          <td colspan="8" class="empty-state">当前周期暂无已出结论且分值有效的设备</td>
        </tr>
      </tbody>
    </table>

    <h3 class="block-title">健康分值缺失对象<span class="block-hint">不参与风险排序，需补录或核实后再定位</span></h3>
    <table class="data-table">
      <thead>
        <tr>
          <th>评估对象</th>
          <th>评估周期</th>
          <th>评估状态</th>
          <th>当前分值</th>
          <th>缺失原因</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in missing" :key="String(row.id)">
          <td>{{ row['评估对象'] }}</td>
          <td>{{ row['评估周期'] }}</td>
          <td>{{ row['评估状态'] }}</td>
          <td><span class="cell-warn">{{ row['健康分值'] || '空' }}</span></td>
          <td class="reason-cell">{{ row['缺失原因'] }}</td>
        </tr>
        <tr v-if="!missing.length">
          <td colspan="5" class="empty-state">没有健康分值缺失的对象</td>
        </tr>
      </tbody>
    </table>

    <section v-if="inconsistencies.length" class="consistency-box">
      <h3 class="block-title">等级 / 结论口径不一致</h3>
      <ul>
        <li v-for="row in inconsistencies" :key="String(row.id)">
          {{ row['评估对象'] }}（{{ row['评估周期'] }}）：记录风险等级为「{{ row['风险等级'] || '空' }}」，
          按健康分值 {{ row['健康分值'] }} 应为「{{ row['应有风险等级'] }}」，请到状态评估页发起复评修正。
        </li>
      </ul>
    </section>

    <footer class="page-foot">
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type RankRow = Record<string, string | number | null>
type MissingRow = Record<string, string | number | null>

const period = ref('')
const periods = ref<string[]>([])
const ranked = ref<RankRow[]>([])
const missing = ref<MissingRow[]>([])
const inconsistencies = ref<RankRow[]>([])
const stats = ref<Record<string, number | null>>({})
const errorMessage = ref('')

const statCards = computed(() => [
  { label: '首次定级', value: stats.value['首次定级'] ?? 0, alert: false },
  { label: '已复评记录', value: stats.value['已复评'] ?? 0, alert: false },
  { label: '高风险设备', value: stats.value['高风险设备'] ?? 0, alert: Number(stats.value['高风险设备'] ?? 0) > 0 },
  { label: '重大/较大/一般/低', value: riskSummary.value, alert: false },
  { label: '健康分值均值', value: stats.value['健康分值均值'] ?? '—', alert: false },
  { label: '分值缺失', value: stats.value['健康分值缺失'] ?? 0, alert: Number(stats.value['健康分值缺失'] ?? 0) > 0 },
])

const riskSummary = computed(() => {
  const dist = (stats.value['风险分布'] ?? null) as Record<string, number> | null
  if (!dist) return '—'
  return [dist['重大风险'] ?? 0, dist['较大风险'] ?? 0, dist['一般风险'] ?? 0, dist['低风险'] ?? 0].join(' / ')
})

function riskKey(level: unknown): string {
  const map: Record<string, string> = {
    重大风险: 'critical',
    较大风险: 'high',
    一般风险: 'medium',
    低风险: 'low',
  }
  return map[String(level ?? '')] ?? ''
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (period.value) query.set('period', period.value)
  try {
    const response = await request(`/api/assess/risk-board?${query.toString()}`)
    if (!response.ok) {
      throw new Error('风险定位数据读取失败')
    }
    const payload = await response.json()
    periods.value = payload['周期选项'] ?? []
    stats.value = payload['统计'] ?? {}
    ranked.value = payload['风险定位'] ?? []
    missing.value = payload['分值缺失'] ?? []
    inconsistencies.value = payload['口径不一致'] ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '风险定位数据读取失败'
  }
}

onMounted(reload)
</script>
