<template>
  <section class="page" data-module="outbound">
    <header class="page-head">
      <div>
        <h2>出库管理管理</h2>
        <p class="page-desc">维护出库单，围绕出库单号、客户名称、货物名称、批次号做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记出库单</button>
        <button
          class="btn"
          type="button"
          :disabled="importing"
          title="选择 CSV 文件，表头需包含：出库单号、客户名称、货物名称、批次号"
          @click="triggerImport"
        >
          {{ importing ? '导入中…' : '批量导入出库单' }}
        </button>
        <button class="btn" type="button" @click="downloadRows">下载出库管理清单</button>
        <input
          ref="fileInput"
          type="file"
          accept=".csv,text/csv"
          hidden
          @change="handleImportFile"
        />
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <section v-if="importResult" class="import-result">
      <header class="import-result-head">
        <strong>{{ importResult.message }}</strong>
        <button class="link" type="button" @click="importResult = null">收起</button>
      </header>
      <p class="import-result-summary">
        共校验 {{ importResult.total }} 行，成功 {{ importResult.imported }} 条，未导入 {{ importResult.failed }} 行
        <span v-if="importResult.aborted">（处理已中止，已导入的部分保留生效）</span>
      </p>
      <table v-if="importResult.failures.length" class="data-table">
        <thead>
          <tr>
            <th>行号</th>
            <th>出库单号</th>
            <th>未导入原因</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="failure in importResult.failures" :key="failure.line">
            <td>{{ failure.line }}</td>
            <td>{{ failure.order_no || '—' }}</td>
            <td>{{ failure.reason }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无出库管理数据，可先登记出库单</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条出库管理记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

interface ImportFailure {
  line: number
  order_no: string
  reason: string
}

interface ImportResult {
  ok: boolean
  message: string
  total: number
  imported: number
  failed: number
  aborted: boolean
  failures: ImportFailure[]
}

const ENDPOINT = '/api/outbound'
const columns = ["出库单号", "客户名称", "货物名称", "批次号", "出库数量", "出库温度", "拣货人", "出库时间"]
const actions = ["确认拣货", "安排发运", "取消出库"]
const statuses = ["待拣货", "已拣货", "已发运", "已取消"]
const stats = [{"label": "今日出库单", "value": 0}, {"label": "待发运单", "value": 0}, {"label": "缺货行数", "value": 0}]
// 与后端 MAX_IMPORT_BYTES 保持一致，超大文件在前端先拦下。
const MAX_IMPORT_BYTES = 2 * 1024 * 1024

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const fileInput = ref<HTMLInputElement | null>(null)
const importing = ref(false)
const importResult = ref<ImportResult | null>(null)

function resetFilters() {
  filters.value = {}
  void reload()
}

function downloadRows() {
  window.open(`${ENDPOINT}/download`, '_blank')
}

function openCreate() {
  errorMessage.value = '出库单登记入口尚未接入审批流'
}

function triggerImport() {
  fileInput.value?.click()
}

async function handleImportFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) {
    return
  }
  errorMessage.value = ''
  importResult.value = null
  if (file.size > MAX_IMPORT_BYTES) {
    errorMessage.value = '文件超过 2MB 上限，请拆分后分批导入'
    return
  }
  importing.value = true
  try {
    const content = await file.text()
    const response = await request(`${ENDPOINT}/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'text/csv; charset=utf-8' },
      body: content,
    })
    const payload = (await response.json()) as ImportResult & { detail?: string }
    if (!response.ok) {
      throw new Error(payload.detail ?? '出库单导入失败，请稍后重试')
    }
    importResult.value = payload
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '出库单导入失败'
  } finally {
    importing.value = false
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('出库管理动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '出库管理操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('出库单列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '出库管理列表读取失败'
  }
}

onMounted(reload)
</script>
