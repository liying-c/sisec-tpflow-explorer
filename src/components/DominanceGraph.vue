<script setup>
// 視圖 3：優勢圖。對每一對系統在 50 首歌上做 Wilcoxon signed-rank 檢定，
// 「A 顯著優於 B」畫成由上往下的邊，經遞移化簡後只剩必要的邊（Hasse diagram）。
// 另有勝率矩陣模式：格子 = A 在幾成的歌上贏過 B。
import { ref, onMounted, watch } from 'vue'
import * as d3 from 'd3'
import { CATEGORY } from '../series.js'
import { showTip, moveTip, hideTip } from '../tooltip.js'

const props = defineProps({
  nodes: { type: Array, required: true },     // [{ system, category, median }] 依中位數排序
  edges: { type: Array, required: true },     // 遞移化簡後 [[a, b]]
  layers: { type: Object, required: true },   // Map system → layer
  win: { type: Function, required: true },    // (a, b) → { rate, p, wins, n }
  selected: { type: Object, required: true },
  metric: { type: String, required: true },
  alpha: { type: Number, default: 0.05 },
  dark: { type: Boolean, default: false },
})
const emit = defineEmits(['select'])

const mode = ref('graph')
const host = ref(null)
const W = 880

function drawGraph(svgHost) {
  const nodes = props.nodes
  const maxLayer = d3.max(nodes, d => props.layers.get(d.system)) ?? 0
  const byLayer = d3.group(nodes, d => props.layers.get(d.system))
  const maxPerLayer = d3.max([...byLayer.values()], l => l.length) ?? 1
  const ML = 36
  const MR = 30
  const ROW = 46
  const TOPPAD = 28
  const H = TOPPAD + Math.max(2, maxPerLayer) * ROW + 10
  const svg = svgHost.attr('viewBox', [0, 0, W, H]).attr('aria-label', '系統優勢圖，左方的系統顯著優於有連線的右方系統')
  const stepX = maxLayer > 0 ? (W - ML - MR) / maxLayer : 0

  // 層由左到右；同一層的系統依中位數由上到下
  const pos = new Map()
  for (const [layer, list] of byLayer) {
    list.sort((a, b) => b.median - a.median)
    const total = list.length * ROW
    const y0 = TOPPAD + (H - TOPPAD - 10 - total) / 2 + ROW / 2
    list.forEach((d, i) => pos.set(d.system, { x: ML + layer * stepX, y: y0 + i * ROW }))
  }

  // 層標籤與淡淡的導引線
  svg.append('g').selectAll('text').data(d3.range(maxLayer + 1)).join('text')
    .attr('class', 'axis-label').attr('text-anchor', 'middle')
    .attr('x', d => ML + d * stepX).attr('y', 12).text(d => (maxLayer > 14 && d % 2 ? '' : `L${d}`))
  svg.append('text').attr('class', 'axis-label').attr('x', W - MR).attr('y', H - 2).attr('text-anchor', 'end').text('← 顯著較好　　　顯著較差 →')

  const edgeSel = svg.append('g').selectAll('path').data(props.edges).join('path')
    .attr('class', 'dom-edge')
    .attr('d', ([a, b]) => {
      const p = pos.get(a), q = pos.get(b)
      const mx = (p.x + q.x) / 2
      return `M${p.x + 9},${p.y} C${mx},${p.y} ${mx},${q.y} ${q.x - 9},${q.y}`
    })

  const g = svg.append('g').selectAll('g').data(nodes, d => d.system).join('g')
    .attr('transform', d => `translate(${pos.get(d.system).x},${pos.get(d.system).y})`)
    .style('cursor', 'pointer')
    .on('click', (e, d) => emit('select', d.system))
    .on('pointerenter', (e, d) => {
      edgeSel.classed('lit', ([a, b]) => a === d.system || b === d.system)
      const better = props.edges.filter(([, b]) => b === d.system).map(([a]) => a)
      const worse = props.edges.filter(([a]) => a === d.system).map(([, b]) => b)
      showTip(e, `<b>${d.system}</b> · ${CATEGORY[d.category].name}<br>${props.metric} 中位數 ${d.median.toFixed(2)} dB · 第 L${props.layers.get(d.system)} 層<br>` +
        `<span class="tip-muted">直接優於：${worse.join('、') || '無'}<br>直接劣於：${better.join('、') || '無'}</span>`)
    })
    .on('pointermove', moveTip)
    .on('pointerleave', () => { edgeSel.classed('lit', false); hideTip() })
  g.append('circle').attr('r', 8).style('fill', d => CATEGORY[d.category].color)
    .attr('class', d => props.selected.has(d.system) ? 'node selected' : 'node')
  g.append('text').attr('class', 'node-label small').attr('text-anchor', 'middle').attr('y', 20).text(d => d.system)
}

function drawMatrix(svgHost) {
  const nodes = props.nodes
  const n = nodes.length
  const ML = 52
  const CS = Math.floor((W - ML - 10) / n)
  const H = ML + n * CS + 10
  const svg = svgHost.attr('viewBox', [0, 0, W, H]).attr('aria-label', '勝率矩陣，列系統在幾成的歌上贏過欄系統')
  // 發散色：紅（多數輸）— 灰（五五波）— 藍（多數贏）；深色模式用對應的深色色階
  const ramp = props.dark ? ['#e66767', '#383835', '#3987e5'] : ['#e34948', '#f0efec', '#2a78d6']
  const color = d3.scaleDiverging([0, 0.5, 1], d3.interpolateRgbBasis(ramp))

  svg.append('g').selectAll('text').data(nodes).join('text')
    .attr('class', 'sys-label small')
    .attr('transform', (d, j) => `translate(${ML + j * CS + CS / 2 + 3},${ML - 6}) rotate(-60)`)
    .text(d => d.system)
  svg.append('g').selectAll('text').data(nodes).join('text')
    .attr('class', 'sys-label small').attr('x', ML - 6).attr('y', (d, i) => ML + i * CS + CS / 2 + 4)
    .attr('text-anchor', 'end').text(d => d.system)

  const cells = []
  nodes.forEach((a, i) => nodes.forEach((b, j) => { if (i !== j) cells.push({ a: a.system, b: b.system, i, j, ...props.win(a.system, b.system) }) }))
  svg.append('g').selectAll('rect').data(cells).join('rect')
    .attr('x', d => ML + d.j * CS + 1).attr('y', d => ML + d.i * CS + 1)
    .attr('width', CS - 2).attr('height', CS - 2).attr('rx', 2)
    .style('fill', d => Number.isFinite(d.rate) ? color(d.rate) : 'var(--surface-2)')
    .attr('class', d => d.p < props.alpha ? 'win-cell' : 'win-cell ns')
    .on('pointerenter', (e, d) => showTip(e, `<b>${d.a}</b> 贏過 <b>${d.b}</b><br>${d.wins} / ${d.n} 首歌（${(d.rate * 100).toFixed(0)}%）<br><span class="tip-muted">Wilcoxon p = ${d.p < 1e-4 ? '< 0.0001' : d.p.toFixed(4)}${d.p < props.alpha ? '，顯著' : '，不顯著（虛線）'}</span>`))
    .on('pointermove', moveTip).on('pointerleave', hideTip)
}

function draw() {
  const el = host.value
  if (!el) return
  d3.select(el).selectAll('*').remove()
  if (!props.nodes.length) return
  const svg = d3.select(el).append('svg').attr('role', 'img')
  if (mode.value === 'graph') drawGraph(svg)
  else drawMatrix(svg)
}

onMounted(draw)
watch(() => [props.nodes, props.edges, props.selected, props.dark, mode.value], draw, { flush: 'post' })
</script>

<template>
  <div>
    <div class="view-tools">
      <div class="seg" role="radiogroup" aria-label="顯示模式">
        <button type="button" role="radio" :aria-checked="mode === 'graph'" :class="{ on: mode === 'graph' }" @click="mode = 'graph'">優勢圖</button>
        <button type="button" role="radio" :aria-checked="mode === 'matrix'" :class="{ on: mode === 'matrix' }" @click="mode = 'matrix'">勝率矩陣</button>
      </div>
      <span class="view-hint" v-if="mode === 'graph'">左方顯著優於右方（Wilcoxon signed-rank，p &lt; {{ alpha }}），已去掉可由遞移推得的邊；L0 = 沒有任何系統顯著優於它</span>
      <span class="view-hint" v-else>列系統在幾成的歌上贏過欄系統；藍 = 多數贏、紅 = 多數輸、灰 = 五五波；虛線框 = 差異不顯著</span>
    </div>
    <div ref="host" class="chart"></div>
  </div>
</template>
