<script setup>
// Cluster heatmap：一張熱圖切片，曲目（欄）以階層式分群重新排序，上方畫樹狀圖。
// 把樹切成 k 群後，群與群之間留白分隔，下方標出每群有幾首歌。
import { ref, onMounted, watch } from 'vue'
import * as d3 from 'd3'
import { CATEGORY } from '../series.js'
import { hclust } from '../tensor.js'
import { showTip, moveTip, hideTip } from '../tooltip.js'

const props = defineProps({
  systems: { type: Array, required: true },    // [{ system, category }] 已排序（列）
  tracks: { type: Array, required: true },     // [{ track_id, artist, title }] 任意順序，本元件會重排
  value: { type: Function, required: true },   // (system, track_id) → 0..1 百分位 | NaN
  raw: { type: Function, required: true },     // (system, track_id) → dB
  k: { type: Number, default: 3 },             // 切成幾群（2–6）
  color: { type: Function, required: true },   // (p) → fill
  metric: { type: String, required: true },
  selected: { type: Object, required: true },  // Set
  selectedTrack: { type: String, default: '' },
})
const emit = defineEmits(['select', 'selectTrack', 'groups'])

const host = ref(null)
const W = 880
const ML = 56
const MT = 6
const DH = 90      // 樹狀圖高度
const DGAP = 4
const RH = 13

// 只有分群結果真的變了才 emit，避免父層存下 groups 後重繪又觸發一次造成迴圈
let lastGroups = null
function emitGroups(groups) {
  const key = JSON.stringify(groups)
  if (key === lastGroups) return
  lastGroups = key
  emit('groups', groups)
}

function draw() {
  const el = host.value
  if (!el) return
  d3.select(el).selectAll('*').remove()
  const ns = props.systems.length
  const n = props.tracks.length
  if (ns < 2 || n < 2) { emitGroups([]); return }

  // ---- 分群：每首歌的特徵 = 它那一欄（各系統的百分位），NaN 以 0.5 代替 ----
  const points = props.tracks.map(t => props.systems.map(s => {
    const v = props.value(s.system, t.track_id)
    return Number.isFinite(v) ? v : 0.5
  }))
  const h = hclust(points)
  const k = Math.max(1, Math.min(Math.round(props.k) || 1, n))
  const label = h.cut(k)
  const pos = new Array(n)                       // 點編號 → 顯示欄位
  h.order.forEach((i, j) => { pos[i] = j })
  const cols = h.order.map((i, j) => ({ track: props.tracks[i], i, j, g: 0 }))
  const groups = []                              // [{ start, end（不含）, ids }]
  cols.forEach((c, j) => {
    if (j === 0 || label[c.i] !== label[cols[j - 1].i]) groups.push({ start: j, end: j, ids: [] })
    const g = groups[groups.length - 1]
    g.end = j + 1
    g.ids.push(c.track.track_id)
    c.g = groups.length - 1
  })
  emitGroups(groups.map(g => g.ids))

  // ---- 版面 ----
  const CW = (W - ML - 4) / n
  const Y0 = MT + DH + DGAP                      // 熱圖頂端
  const HH = ns * RH
  const H = Y0 + HH + 30
  const cx = j => ML + j * CW + CW / 2
  const svg = d3.select(el).append('svg').attr('viewBox', [0, 0, W, H])
    .attr('role', 'img').attr('aria-label', `各系統在各曲目上的 ${props.metric} 百分位，曲目依階層式分群排序並切成 ${groups.length} 群`)

  // ---- 樹狀圖 ----
  const yd = d3.scaleLinear().domain([0, h.root.height || 1]).range([MT + DH, MT])
  const segs = []
  const place = node => {
    if (!node.left) return { x: cx(pos[node.members[0]]), y: yd(0) }
    const a = place(node.left)
    const b = place(node.right)
    const y = yd(node.height)
    segs.push(`M${a.x},${a.y}V${y}H${b.x}V${b.y}`)
    return { x: (a.x + b.x) / 2, y }
  }
  place(h.root)
  svg.append('path').attr('d', segs.join(''))
    .style('fill', 'none').style('stroke', 'var(--text-muted)').style('stroke-width', 1)
    .style('pointer-events', 'none')
  svg.append('text').attr('class', 'axis-label').attr('x', ML - 6).attr('y', MT + 9).attr('text-anchor', 'end').text('差異大')
  svg.append('text').attr('class', 'axis-label').attr('x', ML - 6).attr('y', MT + DH).attr('text-anchor', 'end').text('相似')

  // ---- 熱圖 ----
  const row = svg.append('g').selectAll('g').data(props.systems, d => d.system).join('g')
    .attr('transform', (d, i) => `translate(0,${Y0 + i * RH})`)
  row.append('rect').attr('x', 2).attr('y', 0).attr('width', ML - 6).attr('height', RH).attr('rx', 2)
    .attr('class', d => props.selected.has(d.system) ? 'row-bg selected' : 'row-bg')
    .style('pointer-events', 'all')
    .style('cursor', 'pointer').on('click', (e, d) => emit('select', d.system))
  row.append('rect').attr('x', 6).attr('y', RH / 2 - 4).attr('width', 8).attr('height', 8).attr('rx', 2)
    .style('fill', d => CATEGORY[d.category]?.color ?? 'var(--text-muted)').style('pointer-events', 'none')
  row.append('text').attr('class', 'sys-label small').attr('x', 18).attr('y', RH / 2 + 3.5).text(d => d.system)
    .style('pointer-events', 'none')

  row.selectAll('rect.hm').data(d => cols.map(c => ({ system: d.system, track: c.track, j: c.j, g: c.g, v: props.value(d.system, c.track.track_id) }))).join('rect')
    .attr('class', 'hm')
    .attr('x', d => ML + d.j * CW + 0.5).attr('y', 0.5).attr('width', Math.max(CW - 1, 0.5)).attr('height', RH - 1)
    .style('fill', d => Number.isFinite(d.v) ? props.color(d.v) : 'var(--surface-2)')
    .style('cursor', 'pointer')
    .on('click', (e, d) => emit('selectTrack', d.track.track_id))
    .on('pointerenter', (e, d) => {
      const db = props.raw(d.system, d.track.track_id)
      showTip(e, `<b>${d.system}</b> · ${d.track.artist} – ${d.track.title}<br>${props.metric} ${Number.isFinite(db) ? db.toFixed(2) + ' dB' : '無'}${Number.isFinite(d.v) ? ` · 第 ${Math.round(d.v * 100)} 百分位` : ''}<br><span class="tip-muted">第 ${d.g + 1} 群 · 點擊看逐秒分數</span>`)
    })
    .on('pointermove', moveTip).on('pointerleave', hideTip)

  // ---- 群界線：以底色畫 2px 的線，看起來像留白 ----
  svg.append('g').selectAll('line').data(groups.slice(1)).join('line')
    .attr('x1', d => ML + d.start * CW).attr('x2', d => ML + d.start * CW)
    .attr('y1', Y0 - 1).attr('y2', Y0 + HH + 1)
    .style('stroke', 'var(--surface-1)').style('stroke-width', 2).style('pointer-events', 'none')

  // ---- 選取曲目的欄位高亮 ----
  if (props.selectedTrack) {
    const c = cols.find(d => d.track.track_id === props.selectedTrack)
    if (c) svg.append('rect').attr('class', 'col-hl').attr('x', ML + c.j * CW - 1).attr('y', Y0 - 2)
      .attr('width', CW + 2).attr('height', HH + 4).attr('rx', 3).style('pointer-events', 'none')
  }

  // ---- 每群下方的括號與標籤 ----
  const yb = Y0 + HH + 5
  const gg = svg.append('g').selectAll('g').data(groups).join('g')
  gg.append('path')
    .attr('d', d => { const x0 = ML + d.start * CW + 2, x1 = ML + d.end * CW - 2; return `M${x0},${yb}v4H${x1}v-4` })
    .style('fill', 'none').style('stroke', 'var(--text-muted)').style('stroke-width', 1)
  gg.append('text').attr('class', 'axis-label').attr('text-anchor', 'middle')
    .attr('x', d => ML + (d.start + d.end) / 2 * CW).attr('y', yb + 17)
    // 太窄的群放不下完整文字，只寫群編號（完整資訊在 tooltip）
    .text((d, g) => (d.end - d.start) * CW >= 62 ? `第 ${g + 1} 群 · ${d.ids.length} 首` : `${g + 1}`)
  gg.append('rect').attr('x', d => ML + d.start * CW).attr('y', yb - 2).attr('width', d => (d.end - d.start) * CW).attr('height', 24)
    .style('fill', 'transparent')
    .on('pointerenter', (e, d) => showTip(e, `<b>第 ${groups.indexOf(d) + 1} 群 · ${d.ids.length} 首</b><br><span class="tip-muted">各系統表現型態相近的曲目</span>`))
    .on('pointermove', moveTip).on('pointerleave', hideTip)
}

onMounted(draw)
watch(() => [props.systems, props.tracks, props.value, props.k, props.color, props.selected, props.selectedTrack, props.metric], draw, { flush: 'post' })
</script>

<template>
  <div ref="host" class="chart"></div>
</template>
