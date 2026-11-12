<script setup>
// Small multiples：同一張「系統 × 曲目」熱圖，每個指標各畫一次。
// 每個面板的列、欄順序完全相同，所以可以直接比對同一個位置在不同指標下的深淺。
import { ref, onMounted, watch } from 'vue'
import * as d3 from 'd3'
import { CATEGORY, METRICS } from '../series.js'
import { showTip, moveTip, hideTip } from '../tooltip.js'

const props = defineProps({
  systems: { type: Array, required: true },    // [{ system, category }] 已排序（列）
  tracks: { type: Array, required: true },     // [{ track_id, artist, title }] 已排序（欄）
  metrics: { type: Array, required: true },    // ['SDR', 'SIR', 'SAR', 'ISR']
  value: { type: Function, required: true },   // (system, track_id, metric) → 0..1 百分位 | NaN
  raw: { type: Function, required: true },     // (system, track_id, metric) → dB
  color: { type: Function, required: true },   // (p) → fill
  selected: { type: Object, required: true },  // Set
  selectedTrack: { type: String, default: '' },
})
const emit = defineEmits(['select', 'selectTrack'])

const host = ref(null)
const W = 880
const ML = 56      // 左欄面板的系統標籤寬度
const GAP = 18     // 面板水平間距
const HEAD = 20    // 面板標題高度
const VGAP = 14    // 面板垂直間距
const RH = 7.5

function draw() {
  const el = host.value
  if (!el) return
  d3.select(el).selectAll('*').remove()
  const ns = props.systems.length
  const nt = props.tracks.length
  const nm = props.metrics.length
  if (!ns || !nt || !nm) return

  const cols = nm > 1 ? 2 : 1
  const rows = Math.ceil(nm / cols)
  const PW = (W - ML - 4 - GAP * (cols - 1)) / cols
  const CW = PW / nt
  const PH = ns * RH
  const H = rows * (HEAD + PH) + (rows - 1) * VGAP + 6
  const svg = d3.select(el).append('svg').attr('viewBox', [0, 0, W, H])
    .attr('role', 'img').attr('aria-label', `各系統在各曲目上的 ${props.metrics.join('、')} 百分位，每個指標一個面板`)

  const selTrackJ = props.selectedTrack ? props.tracks.findIndex(t => t.track_id === props.selectedTrack) : -1
  const selRows = props.systems.map((s, i) => ({ s, i })).filter(d => props.selected.has(d.s.system))

  props.metrics.forEach((metric, m) => {
    const c = m % cols
    const r = Math.floor(m / cols)
    const px = ML + c * (PW + GAP)
    const py = r * (HEAD + PH + VGAP) + HEAD
    const panel = svg.append('g').attr('transform', `translate(${px},${py})`)

    // 面板標題：指標 + 說明
    const desc = METRICS.find(d => d.key === metric)?.desc
    const title = panel.append('text').attr('class', 'head on').attr('x', 0).attr('y', -7).text(metric)
    if (desc) title.append('tspan').attr('dx', 6).style('fill', 'var(--text-muted)').style('font-weight', 400).text(desc)

    // 系統標籤只畫在左欄
    if (c === 0) {
      const lab = panel.append('g').selectAll('g').data(props.systems, d => d.system).join('g')
        .attr('transform', (d, i) => `translate(${-ML},${i * RH})`)
        .style('cursor', 'pointer')
        .on('click', (e, d) => emit('select', d.system))
      lab.append('rect').attr('x', 2).attr('y', 0).attr('width', ML - 6).attr('height', RH).attr('rx', 1.5)
        .attr('class', d => props.selected.has(d.system) ? 'row-bg selected' : 'row-bg')
        .style('pointer-events', 'all')
        .append('title').text(d => `${d.system}（${CATEGORY[d.category]?.short ?? d.category}）`)
      lab.append('rect').attr('x', 6).attr('y', RH / 2 - 2.5).attr('width', 5).attr('height', 5).attr('rx', 1)
        .style('fill', d => CATEGORY[d.category]?.color ?? 'var(--text-muted)').style('pointer-events', 'none')
      // 列高只有 7.5px，字級縮到 7px 才不會上下重疊
      lab.append('text').attr('class', 'sys-label small').attr('x', 14).attr('y', RH / 2 + 2.5)
        .style('font-size', '7px').style('pointer-events', 'none').text(d => d.system)
    }

    // 格子
    const row = panel.append('g').selectAll('g').data(props.systems, d => d.system).join('g')
      .attr('transform', (d, i) => `translate(0,${i * RH})`)
    row.selectAll('rect').data(d => props.tracks.map((t, j) => ({ system: d.system, track: t, j, v: props.value(d.system, t.track_id, metric) }))).join('rect')
      .attr('x', d => d.j * CW + 0.25).attr('y', 0.25).attr('width', Math.max(CW - 0.5, 0.5)).attr('height', RH - 0.5)
      .style('fill', d => Number.isFinite(d.v) ? props.color(d.v) : 'var(--surface-2)')
      .style('cursor', 'pointer')
      .on('click', (e, d) => emit('selectTrack', d.track.track_id))
      .on('pointerenter', (e, d) => {
        const db = props.raw(d.system, d.track.track_id, metric)
        showTip(e, `<b>${d.system}</b> · ${d.track.artist} – ${d.track.title}<br>${metric} ${Number.isFinite(db) ? db.toFixed(2) + ' dB' : '無'}${Number.isFinite(d.v) ? ` · 第 ${Math.round(d.v * 100)} 百分位` : ''}<br><span class="tip-muted">點擊看逐秒分數</span>`)
      })
      .on('pointermove', moveTip).on('pointerleave', hideTip)

    // 選取的系統：每個面板都框出整列
    panel.append('g').selectAll('rect').data(selRows).join('rect')
      .attr('x', -0.75).attr('y', d => d.i * RH - 0.5).attr('width', PW + 1.5).attr('height', RH + 1).attr('rx', 1.5)
      .style('fill', 'none').style('stroke', 'var(--select)').style('stroke-width', 1.2)
      .style('pointer-events', 'none')

    // 選取的曲目：每個面板都框出整欄
    if (selTrackJ >= 0) {
      panel.append('rect').attr('class', 'col-hl')
        .attr('x', selTrackJ * CW - 1).attr('y', -2).attr('width', CW + 2).attr('height', PH + 4).attr('rx', 2)
        .style('pointer-events', 'none')
    }
  })
}

onMounted(draw)
watch(() => [props.systems, props.tracks, props.metrics, props.value, props.color, props.selected, props.selectedTrack], draw, { flush: 'post' })
</script>

<template>
  <div ref="host" class="chart"></div>
</template>
