<script setup>
// 階段 4：區塊模式圖（仿 TPFlow 的並列長條圖）。每個維度一組長條，選取的區塊並排。
// 長條 = rank-one 摘要對該元素的平均重建值（百分位）；鬚線 = 原始資料相對於摘要的偏差（Q1–Q3，圓點為中位數）。
import { ref, onMounted, watch } from 'vue'
import * as d3 from 'd3'
import { CATEGORY } from '../series.js'
import { showTip, moveTip, hideTip } from '../tooltip.js'

const props = defineProps({
  // [{ tag: 'A', label, modes: [ Map(key → { model, q1, med, q3 }) × 3 ] }]
  panels: { type: Array, required: true },
  // 每個維度的列：[{ name: '系統', rows: [{ key, label, category? }] }, ...]，順序即顯示順序
  modes: { type: Array, required: true },
  selected: { type: Object, required: true },       // Set of system
  selectedTrack: { type: String, default: '' },
})
const emit = defineEmits(['select', 'selectTrack'])

const host = ref(null)
const W = 880
const ML = 150
const HEAD = 34
const GAP = 26

function draw() {
  const el = host.value
  if (!el) return
  d3.select(el).selectAll('*').remove()
  if (!props.panels.length) return
  const np = props.panels.length
  const colW = (W - ML - 8) / np
  const rowH = m => (m.rows.length > 40 ? 9 : m.rows.length > 10 ? 11 : 18)
  const heights = props.modes.map(m => HEAD + m.rows.length * rowH(m))
  const H = d3.sum(heights) + GAP * (props.modes.length - 1) + 8
  const svg = d3.select(el).append('svg').attr('viewBox', [0, 0, W, H])
    .attr('role', 'img').attr('aria-label', '各區塊在系統、曲目、指標三個維度上的摘要長條圖')
  const x = d3.scaleLinear().domain([0, 1]).range([0, colW - 28])

  let y0 = 0
  props.modes.forEach((mode, mi) => {
    const rh = rowH(mode)
    const g = svg.append('g').attr('transform', `translate(0,${y0})`)
    g.append('text').attr('x', 2).attr('y', 14).attr('class', 'head on').text(`${mode.name}維度`)
    g.append('text').attr('x', 2).attr('y', 27).attr('class', 'axis-label').text(`${mode.rows.length} 列`)

    props.panels.forEach((p, pi) => {
      const gx = ML + pi * colW
      g.append('text').attr('x', gx).attr('y', 14).attr('class', 'head on').text(`${p.tag}　${p.label}`)
      // 0 / 50 / 100 百分位的刻度線
      for (const t of [0, 0.5, 1]) {
        g.append('line').attr('x1', gx + x(t)).attr('x2', gx + x(t)).attr('y1', HEAD - 4).attr('y2', HEAD + mode.rows.length * rh)
          .style('stroke', 'var(--grid)').style('stroke-dasharray', t === 0 ? null : '2 3')
        g.append('text').attr('x', gx + x(t)).attr('y', HEAD - 7).attr('text-anchor', 'middle').attr('class', 'axis-label')
          .style('font-size', '9px').text(t * 100)
      }
    })

    const row = g.append('g').selectAll('g').data(mode.rows, d => d.key).join('g')
      .attr('transform', (d, i) => `translate(0,${HEAD + i * rh})`)
    const isSel = d => (mi === 0 ? props.selected.has(d.key) : mi === 1 ? d.key === props.selectedTrack : false)
    row.append('rect').attr('x', 0).attr('y', 0).attr('width', W - 4).attr('height', rh).attr('rx', 2)
      .attr('class', d => (isSel(d) ? 'row-bg selected' : 'row-bg'))
      .style('cursor', mi < 2 ? 'pointer' : 'default')
      .on('click', (e, d) => { if (mi === 0) emit('select', d.key); else if (mi === 1) emit('selectTrack', d.key) })
    if (mi === 0) row.append('rect').attr('x', 4).attr('y', rh / 2 - 4).attr('width', 8).attr('height', 8).attr('rx', 2)
      .style('fill', d => CATEGORY[d.category].color).style('pointer-events', 'none')
    row.append('text').attr('x', mi === 0 ? 16 : 4).attr('y', rh / 2 + 3.5).attr('class', 'sys-label small')
      .style('font-weight', d => (isSel(d) ? 700 : 500)).style('pointer-events', 'none')
      .text(d => (d.label.length > 24 ? d.label.slice(0, 23) + '…' : d.label))

    props.panels.forEach((p, pi) => {
      const gx = ML + pi * colW
      const cell = row.append('g').attr('transform', `translate(${gx},0)`)
        .datum(d => ({ row: d, s: p.modes[mi].get(d.key) })).filter(d => d.s)
        .style('pointer-events', 'all')
        .on('pointerenter', (e, d) => showTip(e, `<b>${d.row.label}</b> · 區塊 ${p.tag}<br>摘要：第 ${(100 * d.s.model).toFixed(0)} 百分位<br>實際偏差 中位數 ${(100 * d.s.med).toFixed(0)}，Q1–Q3 ${(100 * d.s.q1).toFixed(0)} ～ ${(100 * d.s.q3).toFixed(0)}（百分位點）`))
        .on('pointermove', moveTip).on('pointerleave', hideTip)
      cell.append('rect').attr('x', 0).attr('y', 1).attr('height', rh - 2).attr('rx', 1.5)
        .attr('width', d => Math.max(0, x(Math.min(1, d.s.model))))
        .style('fill', d => (mi === 0 ? CATEGORY[d.row.category].color : 'var(--text-muted)'))
        .style('fill-opacity', 0.85)
      // 偏差鬚線：摘要值 + Q1 到 摘要值 + Q3
      const clamp = v => x(Math.max(0, Math.min(1, v)))
      cell.append('line').attr('y1', rh / 2).attr('y2', rh / 2)
        .attr('x1', d => clamp(d.s.model + d.s.q1)).attr('x2', d => clamp(d.s.model + d.s.q3))
        .style('stroke', 'var(--text-primary)').style('stroke-width', 1)
      cell.append('circle').attr('cy', rh / 2).attr('r', rh > 12 ? 2.4 : 1.7)
        .attr('cx', d => clamp(d.s.model + d.s.med))
        .style('fill', 'var(--text-primary)')
    })
    y0 += heights[mi] + GAP
  })
}

onMounted(draw)
watch(() => [props.panels, props.modes, props.selected, props.selectedTrack], draw, { flush: 'post' })
</script>

<template>
  <div ref="host" class="chart"></div>
</template>
