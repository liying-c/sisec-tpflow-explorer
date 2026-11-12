<script setup>
// 指標錨定散佈圖：每個系統一個點，x / y 各是一個指標的中位數。
// 用來看兩種錯誤之間的取捨（例如漏音少的系統是否人工痕跡多）。點一下選取系統。
import { ref, onMounted, watch } from 'vue'
import * as d3 from 'd3'
import { CATEGORY, METRICS } from '../series.js'
import { showTip, moveTip, hideTip } from '../tooltip.js'

const props = defineProps({
  points: { type: Array, required: true },     // [{ system, category, SDR, SIR, SAR, ISR }] 各系統中位數（dB）
  xMetric: { type: String, required: true },
  yMetric: { type: String, required: true },
  selected: { type: Object, required: true },  // Set
})
const emit = defineEmits(['select'])

const host = ref(null)
const W = 880
const H = 420
const M = { top: 16, right: 24, bottom: 46, left: 56 }

const descOf = key => METRICS.find(m => m.key === key)?.desc ?? ''
const titleOf = key => (descOf(key) ? `${key}（dB） · ${descOf(key)}` : `${key}（dB）`)
const fmt = v => (Number.isFinite(v) ? v.toFixed(2) + ' dB' : '無')

function draw() {
  const el = host.value
  if (!el) return
  d3.select(el).selectAll('*').remove()
  const { xMetric, yMetric } = props
  const pts = props.points.filter(d => Number.isFinite(d[xMetric]) && Number.isFinite(d[yMetric]))
  if (!pts.length) return

  const svg = d3.select(el).append('svg').attr('viewBox', [0, 0, W, H])
    .attr('role', 'img').attr('aria-label', `各系統的 ${xMetric} 與 ${yMetric} 中位數散佈圖`)

  const x = d3.scaleLinear().domain(d3.extent(pts, d => d[xMetric])).nice().range([M.left, W - M.right])
  const y = d3.scaleLinear().domain(d3.extent(pts, d => d[yMetric])).nice().range([H - M.bottom, M.top])
  const iw = W - M.left - M.right
  const ih = H - M.top - M.bottom

  // 格線
  svg.append('g').attr('class', 'grid').attr('transform', `translate(0,${H - M.bottom})`)
    .call(d3.axisBottom(x).ticks(8).tickSize(-ih).tickFormat(''))
  svg.append('g').attr('class', 'grid').attr('transform', `translate(${M.left},0)`)
    .call(d3.axisLeft(y).ticks(6).tickSize(-iw).tickFormat(''))
  // 座標軸
  svg.append('g').attr('class', 'axis').attr('transform', `translate(0,${H - M.bottom})`)
    .call(d3.axisBottom(x).ticks(8).tickSizeOuter(0))
  svg.append('g').attr('class', 'axis').attr('transform', `translate(${M.left},0)`)
    .call(d3.axisLeft(y).ticks(6).tickSizeOuter(0))
  // 軸標題
  svg.append('text').attr('class', 'axis-label').attr('x', M.left + iw / 2).attr('y', H - 8)
    .attr('text-anchor', 'middle').text(titleOf(xMetric))
  svg.append('text').attr('class', 'axis-label')
    .attr('transform', `translate(14,${M.top + ih / 2}) rotate(-90)`)
    .attr('text-anchor', 'middle').text(titleOf(yMetric))

  // 選取的點畫在最上層
  const ordered = [...pts].sort((a, b) => props.selected.has(a.system) - props.selected.has(b.system))

  svg.append('g').selectAll('circle').data(ordered, d => d.system).join('circle')
    .attr('class', d => props.selected.has(d.system) ? 'node selected' : 'node')
    .attr('cx', d => x(d[xMetric])).attr('cy', d => y(d[yMetric])).attr('r', 6)
    .style('fill', d => CATEGORY[d.category]?.color ?? 'var(--text-muted)')
    .style('cursor', 'pointer')
    .on('click', (e, d) => emit('select', d.system))
    .on('pointerenter', (e, d) => showTip(e, `<b>${d.system}</b> · ${CATEGORY[d.category]?.short ?? d.category}<br>${xMetric} ${fmt(d[xMetric])}<br>${yMetric} ${fmt(d[yMetric])}<br><span class="tip-muted">點擊選取 / 取消選取</span>`))
    .on('pointermove', moveTip).on('pointerleave', hideTip)

  // 標籤：oracle（含 MIX）與已選取的系統一律標名；右側 15% 的點把標籤放左邊
  const flipAt = M.left + iw * 0.85
  svg.append('g').selectAll('text')
    .data(ordered.filter(d => d.category === 'oracle' || props.selected.has(d.system)), d => d.system).join('text')
    .attr('class', 'node-label')
    .attr('x', d => x(d[xMetric]) + (x(d[xMetric]) > flipAt ? -10 : 10))
    .attr('y', d => y(d[yMetric]) + 3.5)
    .attr('text-anchor', d => x(d[xMetric]) > flipAt ? 'end' : 'start')
    // 底色描邊，讓標籤壓在格線或其他點上時仍可讀
    .style('paint-order', 'stroke').style('stroke', 'var(--surface-1)').style('stroke-width', 3)
    .style('stroke-linejoin', 'round')
    .text(d => d.system)
}

onMounted(draw)
watch(() => [props.points, props.xMetric, props.yMetric, props.selected], draw, { flush: 'post' })
</script>

<template>
  <div ref="host" class="chart"></div>
</template>
