<script setup>
// 階段 4：分割樹（仿 TPFlow 的 Tree View）。每張卡片是一塊子張量；
// 長條 = rank-one 摘要沒解釋到的比例（越短代表摘要越忠實）。點卡片選取，最多三塊並排比較。
import { ref, onMounted, watch } from 'vue'
import * as d3 from 'd3'
import { showTip, moveTip, hideTip } from '../tooltip.js'

const props = defineProps({
  // [{ id, parentId, depth, label, sizes: '31 個系統 × 50 首歌 × 4 個指標', unexplained: 0–1, splitLabel: '依曲目分成 3 群' | '', note: '' }]
  nodes: { type: Array, required: true },
  tags: { type: Object, required: true },     // Map: node id → 'A' | 'B' | 'C'
  focusId: { type: Number, default: -1 },
})
const emit = defineEmits(['pick'])

const host = ref(null)
const W = 880
const CARD_W = 232
const CARD_H = 62
const GAP_Y = 12

function draw() {
  const el = host.value
  if (!el) return
  d3.select(el).selectAll('*').remove()
  if (!props.nodes.length) return

  const root = d3.stratify().id(d => d.id).parentId(d => d.parentId)(props.nodes)
  const depth = root.height
  const colW = depth ? Math.min(300, (W - CARD_W) / depth) : 0
  d3.tree().nodeSize([CARD_H + GAP_Y, colW]).separation(() => 1)(root)
  const xs = root.descendants().map(d => d.x)
  const top = d3.min(xs), H = d3.max(xs) - top + CARD_H + 8
  const svg = d3.select(el).append('svg').attr('viewBox', [0, 0, W, H])
    .attr('role', 'img').attr('aria-label', '分割樹：每個節點是一塊資料，長條是摘要沒解釋到的比例')
  const px = d => d.y, py = d => d.x - top + 4

  svg.append('g').selectAll('path').data(root.links()).join('path')
    .attr('d', l => {
      const x0 = px(l.source) + CARD_W, y0 = py(l.source) + CARD_H / 2, x1 = px(l.target), y1 = py(l.target) + CARD_H / 2
      const mx = (x0 + x1) / 2
      return `M${x0},${y0}C${mx},${y0} ${mx},${y1} ${x1},${y1}`
    })
    .style('fill', 'none').style('stroke', 'var(--text-muted)').style('stroke-opacity', 0.6).style('stroke-width', 1.2)

  const maxU = Math.max(0.05, d3.max(props.nodes, d => d.unexplained))
  const bar = d3.scaleLinear().domain([0, maxU]).range([0, CARD_W - 98])

  const g = svg.append('g').selectAll('g').data(root.descendants(), d => d.id).join('g')
    .attr('transform', d => `translate(${px(d)},${py(d)})`)
    .style('cursor', 'pointer')
    .on('click', (e, d) => emit('pick', d.data.id))
    .on('pointerenter', (e, d) => showTip(e, `<b>${d.data.label}</b><br>${d.data.sizes}<br>摘要沒解釋到 ${(100 * d.data.unexplained).toFixed(1)}%${d.data.splitLabel ? '<br>' + d.data.splitLabel : ''}<br><span class="tip-muted">點擊選取，最多三塊並排比較</span>`))
    .on('pointermove', moveTip).on('pointerleave', hideTip)

  g.append('rect').attr('width', CARD_W).attr('height', CARD_H).attr('rx', 6)
    .style('fill', 'var(--surface-2)')
    .style('stroke', d => (props.tags.has(d.data.id) ? 'var(--select)' : 'var(--grid)'))
    .style('stroke-width', d => (d.data.id === props.focusId ? 2.4 : props.tags.has(d.data.id) ? 1.6 : 1))

  g.append('text').attr('x', 10).attr('y', 17).attr('class', 'sys-label').text(d => d.data.label)
  g.append('text').attr('x', 10).attr('y', 31).attr('class', 'axis-label').text(d => d.data.sizes)

  // 未解釋比例：長條 + 數字
  g.append('rect').attr('x', 10).attr('y', 39).attr('width', CARD_W - 98).attr('height', 7).attr('rx', 2)
    .style('fill', 'var(--surface-1)').style('stroke', 'var(--grid)')
  g.append('rect').attr('x', 10).attr('y', 39).attr('width', d => bar(d.data.unexplained)).attr('height', 7).attr('rx', 2)
    .style('fill', 'var(--text-secondary)')
  g.append('text').attr('x', CARD_W - 82).attr('y', 46).attr('class', 'axis-label')
    .text(d => `未解釋 ${(100 * d.data.unexplained).toFixed(1)}%`)
  g.append('text').attr('x', 10).attr('y', 57).attr('class', 'axis-label').text(d => d.data.note || d.data.splitLabel)

  // 比較標籤 A / B / C
  const tagged = g.filter(d => props.tags.has(d.data.id))
  tagged.append('rect').attr('x', CARD_W - 26).attr('y', 6).attr('width', 18).attr('height', 18).attr('rx', 4)
    .style('fill', 'var(--text-primary)')
  tagged.append('text').attr('x', CARD_W - 17).attr('y', 19).attr('text-anchor', 'middle')
    .style('fill', 'var(--surface-1)').style('font-size', '11.5px').style('font-weight', 700)
    .text(d => props.tags.get(d.data.id))
}

onMounted(draw)
watch(() => [props.nodes, props.tags, props.focusId], draw, { flush: 'post' })
</script>

<template>
  <div ref="host" class="chart"></div>
</template>
