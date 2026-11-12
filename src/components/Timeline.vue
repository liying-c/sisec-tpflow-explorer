<script setup>
// 視圖 5：逐秒時間線。選到一首歌後載入它的逐秒分數，畫出被選系統（未選則畫排行前 5）在這首歌上的指標變化。
// 在圖上拖曳可放大時間範圍，雙擊還原；滑鼠移動顯示十字線與各系統當秒的分數。
import { ref, onMounted, watch } from 'vue'
import * as d3 from 'd3'
import { CATEGORY } from '../series.js'
import { showTip, moveTip, hideTip } from '../tooltip.js'

const props = defineProps({
  frames: { type: Array, default: null },      // [{ system, target, time, SDR, ... }]
  systems: { type: Array, required: true },    // [{ system, category }] 要畫的系統
  target: { type: String, required: true },
  metric: { type: String, required: true },
  trackLabel: { type: String, default: '' },
})

const host = ref(null)
const W = 880
const H = 260
const ML = 48
const MR = 90
const MT = 24
const MB = 36
let zoom = null   // [t0, t1] 或 null

function draw() {
  const el = host.value
  if (!el) return
  d3.select(el).selectAll('*').remove()
  if (!props.frames) return
  const series = props.systems.map(s => ({
    ...s,
    rows: props.frames.filter(r => r.system === s.system && r.target === props.target && Number.isFinite(r[props.metric])),
  })).filter(s => s.rows.length)
  if (!series.length) return

  const tMax = d3.max(props.frames, r => r.time)
  const svg = d3.select(el).append('svg').attr('viewBox', [0, 0, W, H])
    .attr('role', 'img').attr('aria-label', `${props.trackLabel} 的逐秒 ${props.metric}`)
  const x = d3.scaleLinear().domain(zoom ?? [0, tMax]).range([ML, W - MR])
  const all = series.flatMap(s => s.rows.filter(r => r.time >= x.domain()[0] && r.time <= x.domain()[1]).map(r => r[props.metric]))
  const y = d3.scaleLinear().domain([Math.min(-5, d3.quantile(all.sort(d3.ascending), 0.02) ?? -5), d3.max(all) ?? 10]).nice().range([H - MB, MT])

  svg.append('g').attr('class', 'grid').attr('transform', `translate(${ML},0)`)
    .call(d3.axisLeft(y).ticks(5).tickSize(-(W - ML - MR)).tickFormat(''))
  svg.append('g').attr('class', 'axis').attr('transform', `translate(${ML},0)`)
    .call(d3.axisLeft(y).ticks(5).tickSize(4)).call(g => g.select('.domain').remove())
  svg.append('g').attr('class', 'axis').attr('transform', `translate(0,${H - MB})`)
    .call(d3.axisBottom(x).ticks(10).tickSize(4)).call(g => g.select('.domain').remove())
  svg.append('text').attr('class', 'axis-label').attr('x', W - MR).attr('y', H - 6).attr('text-anchor', 'end').text('時間 (秒)')
  svg.append('text').attr('class', 'axis-label').attr('x', ML - 40).attr('y', 12).text(`${props.metric} (dB)`)

  const clip = svg.append('clipPath').attr('id', 'tl-clip').append('rect').attr('x', ML).attr('y', 0).attr('width', W - ML - MR).attr('height', H - MB)
  const line = d3.line().defined(r => Number.isFinite(r[props.metric])).x(r => x(r.time)).y(r => y(Math.max(y.domain()[0], r[props.metric])))
  const paths = svg.append('g').attr('clip-path', 'url(#tl-clip)').selectAll('path').data(series).join('path')
    .attr('fill', 'none').attr('stroke-width', 2).attr('stroke-linejoin', 'round')
    .style('stroke', s => CATEGORY[s.category].color).attr('d', s => line(s.rows))

  // 直接標籤：線尾寫系統名（同類別顏色相同，靠文字辨識）
  const [t0, t1] = x.domain()
  const ends = series.map(s => {
    const last = s.rows.filter(r => r.time <= t1 && r.time >= t0).at(-1)
    return { system: s.system, y: last ? y(Math.max(y.domain()[0], last[props.metric])) : NaN }
  }).filter(d => Number.isFinite(d.y)).sort((a, b) => a.y - b.y)
  for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 12) ends[i].y = ends[i - 1].y + 12   // 避免標籤重疊
  svg.append('g').selectAll('text').data(ends).join('text').attr('class', 'node-label')
    .attr('x', W - MR + 6).attr('y', d => d.y + 4).text(d => d.system)

  // 十字線 + tooltip
  const cross = svg.append('line').attr('class', 'crosshair').attr('y1', MT).attr('y2', H - MB).style('display', 'none')
  const overlay = svg.append('rect').attr('x', ML).attr('y', MT).attr('width', W - ML - MR).attr('height', H - MB - MT)
    .attr('fill', 'transparent').style('cursor', 'crosshair')
  overlay.on('pointermove', e => {
    const [mx] = d3.pointer(e)
    const t = Math.round(x.invert(mx))
    cross.style('display', null).attr('x1', x(t)).attr('x2', x(t))
    const rows = series.map(s => { const r = s.rows.find(r => r.time === t); return r ? `${s.system}: ${r[props.metric].toFixed(1)}` : null }).filter(Boolean)
    showTip(e, `<b>${t} 秒</b><br>${rows.join('<br>')}`)
  }).on('pointerleave', () => { cross.style('display', 'none'); hideTip() })

  // brush 放大
  const brush = d3.brushX().extent([[ML, MT], [W - MR, H - MB]]).on('end', e => {
    if (!e.sourceEvent) return
    if (!e.selection) return
    zoom = e.selection.map(x.invert)
    draw()
  })
  svg.append('g').attr('class', 'brush').call(brush)
  svg.on('dblclick', () => { zoom = null; draw() })
  paths.raise()
  overlay.raise()
}

onMounted(draw)
watch(() => [props.frames, props.systems, props.target, props.metric], () => { zoom = null; draw() }, { flush: 'post' })
</script>

<template>
  <div ref="host" class="chart"></div>
</template>
