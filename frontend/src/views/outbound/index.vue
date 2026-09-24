<template>
  <section class="page" data-module="outbound">
    <header class="page-head">
      <div>
        <h2>出库管理管理</h2>
        <p class="page-desc">维护出库单，围绕出库单号、客户名称、货物名称、批次号做登记、筛选与状态流转；支持上传 CSV 表格批量导入，问题行会单独列出原因。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记出库单</button>
        <button class="btn" type="button" :disabled="importing" @click="triggerImport">
          {{ importing ? '导入中…' : '批量导入' }}
        </button>
        <button class="btn" type="button" @click="exportRows">导出出库管理清单</button>
        <input ref="fileInput" type="file" accept=".csv,.tsv,.txt" hidden @change="onImportFile" />
      </div>
    </header>

    <section v-if="importResult" class="import-result">
      <header class="import-result-head">
        <span>{{ importResult.message }}</span>
        <button class="link" type="button" @click="importResult = null">收起</button>
      </header>
      <p v-if="importResult.aborted" class="import-abort">
        导入已中途停止，成功部分已保留；修正后重新上传时，已生效的出库单号会自动跳过。
      </p>
      <table v-if="importResult.failed.length" class="data-table import-failed-table">
        <thead>
          <tr>
            <th>行号</th>
            <th>出库单号</th>
            <th>批次号</th>
            <th>未导入原因</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in importResult.failed" :key="item.line">
            <td>{{ item.line }}</td>
            <td>{{ item.values['出库单号'] || '—' }}</td>
            <td>{{ item.values['批次号'] || '—' }}</td>
            <td>{{ item.reason }}</td>
          </tr>
        </tbody>
      </table>
    </section>

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
type ImportFailure = { line: number; reason: string; values: Record<string, string> }
type ImportResult = {
  ok: boolean
  message: string
  imported: number
  aborted: boolean
  failed: ImportFailure[]
}

const ENDPOINT = '/api/outbound'
const columns = ["出库单号", "客户名称", "货物名称", "批次号", "出库数量", "出库温度", "拣货人", "出库时间"]
const actions = ["确认拣货", "安排发运", "取消出库"]
const statuses = ["待拣货", "已拣货", "已发运", "已取消"]
const stats = [{"label": "今日出库单", "value": 0}, {"label": "待发运单", "value": 0}, {"label": "缺货行数", "value": 0}]

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

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '出库单登记入口尚未接入审批流'
}

function triggerImport() {
  fileInput.value?.click()
}

async function onImportFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = '' // 允许选择同一文件重试，已生效的行会被后端跳过
  if (!file) {
    return
  }
  errorMessage.value = ''
  importResult.value = null
  importing.value = true
  try {
    const formData = new FormData()
    formData.append('file', file)
    const response = await request(`${ENDPOINT}/import`, {
      method: 'POST',
      headers: {},
      body: formData,
    })
    const payload = (await response.json()) as ImportResult
    if (!response.ok) {
      throw new Error(payload.message || '出库单导入失败')
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
      body: JSON.stringify({ values: { action } }),
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
