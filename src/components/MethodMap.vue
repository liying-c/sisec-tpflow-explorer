<script setup>
// 視圖 2：方法地圖。每個系統一個點，位置由 MDS 算出（距離 = 1 − 分數剖面的相關係數），
// 靠近 = 在同樣的歌上同樣好或同樣壞。邊 = 兩個系統有共同作者（真實關係）。
import { ref, onMounted, watch } from 'vue'
import * as d3 from 'd3'
import { CATEGORY } from '../series.js'
import { showTip, moveTip, hideTip } from '../tooltip.js'

const props = defineProps({
  points: { type: Array, required: true },   // [{ system, category, x, y, median, info }]
  edges: { type: Array, required: true },    // [{ a, b, shared: [names] }]
  selected: { type: Object, required: true },
  metric: { type: String, required: true },
})
const emit = defineEmits(['select'])

const host = ref(null)
const W = 440
const H = 480
const PAD = 36

function draw() {
  const el = host.value
  if (!el) return
  d3.select(el).selectAll('*').remove()
  if (!props.points.length) return

  const svg = d3.select(el).append('svg').attr('viewBox', [0, 0, W, H])
    .attr('role', 'img').attr('aria-label', '系統相似度地圖，點越近表示在同樣的歌上表現越相似，連線表示共同作者')

  const x = d3.scaleLinear().domain(d3.extent(props.points, d => d.x)).nice().range([PAD, W - PAD])
  const y = d3.scaleLinear().domain(d3.extent(props.points, d => d.y)).nice().range([H - PAD, PAD])

  // 用一個短的力模擬把重疊的點推開（JY1 與 JY2 幾乎同一點），但仍錨定在 MDS 座標附近
  const nodes = props.points.map(d => ({ ...d, fx0: x(d.x), fy0: y(d.y), x: x(d.x), y: y(d.y) }))
  const sim = d3.forceSimulation(nodes)
    .force('x', d3.forceX(d => d.fx0).strength(0.6))
    .force('y', d3.forceY(d => d.fy0).strength(0.6))
    .force('collide', d3.forceCollide(17))
    .stop()
  for (let i = 0; i < 200; i++) sim.tick()
  const pos = new Map(nodes.map(n => [n.system, n]))

  svg.append('text').attr('class', 'axis-label').attr('x', PAD).attr('y', H - 10).text('MDS 第 1 維（座標無物理意義，只表示相對距離）')

  // 作者關係的邊
  svg.append('g').selectAll('line').data(props.edges.filter(e => pos.has(e.a) && pos.has(e.b))).join('line')
    .attr('class', 'author-edge')
    .attr('x1', e => pos.get(e.a).x).attr('y1', e => pos.get(e.a).y)
    .attr('x2', e => pos.get(e.b).x).attr('y2', e => pos.get(e.b).y)
    .attr('stroke-width', e => Math.min(4, 1 + e.shared.length))
    .on('pointerenter', (ev, e) => showTip(ev, `<b>${e.a} — ${e.b}</b><br>共同作者：${e.shared.join('、')}`))
    .on('pointermove', moveTip).on('pointerleave', hideTip)

  const g = svg.append('g').selectAll('g').data(nodes, d => d.system).join('g')
    .attr('transform', d => `translate(${d.x},${d.y})`)
    .style('cursor', 'pointer')
    .on('click', (e, d) => emit('select', d.system))
    .on('pointerenter', (e, d) => showTip(e, `<b>${d.system}</b> · ${CATEGORY[d.category].name}<br>${props.metric} 中位數 ${Number.isFinite(d.median) ? d.median.toFixed(2) + ' dB' : '無'}<br><span class="tip-muted">${d.info.authors}</span><br><span class="tip-muted">${d.info.affiliation}</span>`))
    .on('pointermove', moveTip).on('pointerleave', hideTip)

  g.append('circle').attr('r', d => props.selected.has(d.system) ? 9 : 7)
    .style('fill', d => CATEGORY[d.category].color)
    .attr('class', d => props.selected.has(d.system) ? 'node selected' : 'node')
  g.append('text').attr('class', 'node-label small').attr('x', 9).attr('y', 3.5).text(d => d.system)
}

onMounted(draw)
watch(() => [props.points, props.edges, props.selected], draw, { flush: 'post' })
</script>

<template>
  <div ref="host" class="chart"></div>
</template>
