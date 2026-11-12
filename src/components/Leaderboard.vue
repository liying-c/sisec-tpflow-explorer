<script setup>
// 視圖 1：排行榜熱圖（系統 × stem）。格子 = 該指標在 50 首歌的中位數。
// 點欄位標題切換全域 stem（並依它排序）；點列選取系統。
import { ref, onMounted, watch } from 'vue'
import * as d3 from 'd3'
import { CATEGORY, TARGETS } from '../series.js'
import { showTip, moveTip, hideTip } from '../tooltip.js'

const props = defineProps({
  rows: { type: Array, required: true },       // [{ system, category, values: { vocals: med, ... } }] 已排序
  target: { type: String, required: true },
  metric: { type: String, required: true },
  selected: { type: Object, required: true },  // Set
  color: { type: Function, required: true },   // value → fill
  textOn: { type: Function, required: true },  // fill → text color
})
const emit = defineEmits(['select', 'setTarget'])

const host = ref(null)
const W = 440
const ML = 64
const CW = 70
const RH = 21
const HEAD = 30

function draw() {
  const el = host.value
  if (!el) return
  d3.select(el).selectAll('*').remove()
  const H = HEAD + props.rows.length * RH + 6
  const svg = d3.select(el).append('svg').attr('viewBox', [0, 0, W, H])
    .attr('role', 'img').attr('aria-label', `各系統在五個 stem 的 ${props.metric} 中位數排行榜`)

  // 欄位標題（可點擊）
  TARGETS.forEach((t, j) => {
    const g = svg.append('g').attr('class', 'col-head').attr('transform', `translate(${ML + j * CW + CW / 2},${HEAD - 10})`)
      .style('cursor', 'pointer').on('click', () => emit('setTarget', t.key))
    g.append('text').attr('text-anchor', 'middle').attr('class', props.target === t.key ? 'head on' : 'head')
      .text(t.key + (props.target === t.key ? ' ▾' : ''))
    g.append('title').text(`依 ${t.name} 排序並切換全域 stem`)
  })

  const row = svg.append('g').selectAll('g').data(props.rows, d => d.system).join('g')
    .attr('transform', (d, i) => `translate(0,${HEAD + i * RH})`)
    .style('cursor', 'pointer')
    .on('click', (e, d) => emit('select', d.system))

  // 列背景（選取時高亮）
  row.append('rect').attr('x', 2).attr('y', 1).attr('width', W - 4).attr('height', RH - 2).attr('rx', 3)
    .attr('class', d => props.selected.has(d.system) ? 'row-bg selected' : 'row-bg')

  row.append('rect').attr('x', 8).attr('y', RH / 2 - 5).attr('width', 10).attr('height', 10).attr('rx', 2)
    .style('fill', d => CATEGORY[d.category].color)
  row.append('text').attr('x', 22).attr('y', RH / 2 + 4).attr('class', 'sys-label')
    .text(d => d.system)

  // 格子
  const cell = row.selectAll('g.cell').data(d => TARGETS.map(t => ({ system: d.system, target: t.key, value: d.values[t.key] }))).join('g')
    .attr('class', 'cell').attr('transform', (d, j) => `translate(${ML + j * CW},0)`)
  cell.append('rect').attr('x', 1).attr('y', 1).attr('width', CW - 2).attr('height', RH - 2).attr('rx', 3)
    .style('fill', d => Number.isFinite(d.value) ? props.color(d.value) : 'var(--surface-2)')
  cell.append('text').attr('x', CW / 2).attr('y', RH / 2 + 4).attr('text-anchor', 'middle').attr('class', 'cell-text')
    .style('fill', d => Number.isFinite(d.value) ? props.textOn(props.color(d.value)) : 'var(--text-muted)')
    .text(d => Number.isFinite(d.value) ? d.value.toFixed(1) : '–')
  cell.on('pointerenter', (e, d) => showTip(e, `<b>${d.system}</b> · ${d.target}<br>${props.metric} 中位數 ${Number.isFinite(d.value) ? d.value.toFixed(2) + ' dB' : '無'}`))
    .on('pointermove', moveTip).on('pointerleave', hideTip)
}

onMounted(draw)
watch(() => [props.rows, props.target, props.metric, props.selected], draw, { flush: 'post' })
</script>

<template>
  <div ref="host" class="chart"></div>
</template>
