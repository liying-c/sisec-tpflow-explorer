<script setup>
import { ref, shallowRef, computed, watch, onMounted } from 'vue'
import * as d3 from 'd3'
import ControlBar from './components/ControlBar.vue'
import Leaderboard from './components/Leaderboard.vue'
import MethodMap from './components/MethodMap.vue'
import DominanceGraph from './components/DominanceGraph.vue'
import TrackHeatmap from './components/TrackHeatmap.vue'
import Timeline from './components/Timeline.vue'
import MetricAnchor from './components/MetricAnchor.vue'
import SmallMultiples from './components/SmallMultiples.vue'
import ClusterHeatmap from './components/ClusterHeatmap.vue'
import PartitionTree from './components/PartitionTree.vue'
import PatternBars from './components/PatternBars.vue'
import { api, loadFrames } from './api.js'
import { latest } from './latest.js'
import { CATEGORIES, CATEGORY, METRICS, TARGETS, MODE_NAMES, MODE_UNITS } from './series.js'
import { tip } from './tooltip.js'

// 這個檔只管狀態與畫面；統計、張量、圖論的計算都在後端（backend/sisec），透過 api.js 取得結果。
const ALPHA = 0.05
const isNum = v => typeof v === 'number' && Number.isFinite(v)

// ---------- 狀態 ----------
const loading = ref(true)
const error = ref('')
const metric = ref('SDR')
const target = ref('vocals')
const cats = ref(new Set(CATEGORIES.map(c => c.key)))
const selected = ref(new Set())
const selectedTrack = ref('')
const frames = ref(null)
const dark = ref(window.matchMedia('(prefers-color-scheme: dark)').matches)
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => { dark.value = e.matches })

// 網址參數：?m=SDR&s=vocals&c=supervised,blind&sel=TAK2,UHL3&t=track-id
const q = new URLSearchParams(location.search)
if (METRICS.some(m => m.key === q.get('m'))) metric.value = q.get('m')
if (TARGETS.some(t => t.key === q.get('s'))) target.value = q.get('s')
if (q.get('c')) { const c = new Set(q.get('c').split(',').filter(k => CATEGORY[k])); if (c.size) cats.value = c }
if (q.get('sel')) selected.value = new Set(q.get('sel').split(',').filter(Boolean))
if (q.get('t')) selectedTrack.value = q.get('t')

// ---------- 後端回應 ----------
const meta = shallowRef(null)   // { systems, tracks }
const ov = shallowRef(null)     // 階段 1：{ metric, target, ...overview }，一個指標、一個 stem
const st = shallowRef(null)     // 階段 2–4：人聲的列、欄、百分位
const cl = shallowRef(null)     // 圖 6：{ metric, order, merges, labels }
const busy = ref(0)             // 進行中的請求數
const apiError = ref('')
const describe = e => `無法連上計算伺服器（${e.message}）。若伺服器剛喚醒，請稍候重新整理。`
const scope = () => ({ categories: [...cats.value] })

// 執行一個請求並維護「計算中」與錯誤訊息。失敗時保留上一次的畫面；strict 時改為往外丟（首次載入用）。
async function call(task, strict = false) {
  busy.value++
  try {
    const result = await task()
    apiError.value = ''
    return result
  } catch (e) {
    if (strict) throw e
    apiError.value = describe(e)
  } finally {
    busy.value--
  }
}

const data = computed(() => meta.value && {
  systemInfo: new Map(meta.value.systems.map(s => [s.system, s])),
  trackInfo: new Map(meta.value.tracks.map(t => [t.track_id, t])),
})

// ---------- 階段 1：排行、熱圖、方法地圖、優勢圖 ----------
const fetchOverview = latest(api.overview)
async function refreshOverview(strict = false) {
  const query = { metric: metric.value, target: target.value, ...scope() }
  const r = await call(() => fetchOverview(query), strict)
  if (r) ov.value = { ...r, metric: query.metric, target: query.target }
}
watch([metric, target, cats], () => { if (meta.value) refreshOverview() })

// 圖上標示的指標與 stem 跟著「已經拿到的資料」走，回應還沒到之前不會出現標題與內容不一致
const viewMetric = computed(() => ov.value?.metric ?? metric.value)
const viewTarget = computed(() => ov.value?.target ?? target.value)

const trackIndex = computed(() => new Map((ov.value?.trackIds ?? []).map((t, i) => [t, i])))
const ranking = computed(() => ov.value?.ranking ?? [])
const leaderboardRows = computed(() => ov.value?.leaderboard ?? [])
const tracksSorted = computed(() => ov.value?.tracksSorted ?? [])
const valueAt = (system, trackId) => ov.value?.profiles[system]?.[trackIndex.value.get(trackId)] ?? NaN

// 顏色：單色漸層（藍），低 → 高。深色模式用同一組色階反向，讓「高」是亮的。
const SEQ_LIGHT = ['#cde2fb', '#86b6ef', '#3987e5', '#1c5cab', '#0d366b']
const SEQ_DARK = ['#184f95', '#256abf', '#3987e5', '#86b6ef', '#cde2fb']
const color = computed(() => {
  const sc = d3.scaleSequential(d3.interpolateRgbBasis(dark.value ? SEQ_DARK : SEQ_LIGHT)).domain(ov.value?.colorDomain ?? [0, 10]).clamp(true)
  return v => sc(v)
})
const textOn = fill => (d3.hsl(fill).l > 0.62 ? '#0b0b0b' : '#ffffff')

const mapPoints = computed(() => (ov.value?.map ?? []).map(p => ({ ...p, info: data.value.systemInfo.get(p.system) })))
const authorEdges = computed(() => ov.value?.authorEdges ?? [])

// 優勢圖：後端回傳依排行順序的勝場、樣本數、p 值矩陣，這裡包成 (a, b) → 結果 的查表
const dominance = computed(() => {
  const d = ov.value?.dominance
  if (!d) return { win: () => ({ wins: 0, n: 0, rate: NaN, p: 1 }), edges: [], allEdges: 0, layers: new Map() }
  const at = new Map(d.order.map((s, i) => [s, i]))
  const win = (a, b) => {
    const i = at.get(a), j = at.get(b)
    const wins = d.wins[i][j], n = d.n[i][j]
    return { wins, n, rate: n ? wins / n : NaN, p: d.p[i][j] }
  }
  return { win, edges: d.edges, allEdges: d.allEdges, layers: new Map(Object.entries(d.layers)) }
})

// 時間線要畫的系統 = 已選取者，否則排行前 5
const timelineSystems = computed(() => {
  const picked = ranking.value.filter(r => selected.value.has(r.system))
  return picked.length ? picked : ranking.value.slice(0, 5)
})
const selectedTrackInfo = computed(() => data.value?.trackInfo.get(selectedTrack.value))
watch([selectedTrack, meta], async ([t]) => {
  frames.value = null
  if (!t || !meta.value) return
  try { frames.value = await loadFrames(t) } catch { frames.value = null }
}, { immediate: true })


// ================= 階段 2–4：固定看人聲（唯一涵蓋全部 31 個系統的目標） =================
const METRIC_KEYS = METRICS.map(m => m.key)
const metricAt = new Map(METRIC_KEYS.map((m, i) => [m, i]))
const range = n => Array.from({ length: n }, (_, i) => i)

// 列與欄固定用人聲 SDR 的排行與曲目難度，不隨控制列的指標改變
const stageSystems = computed(() => st.value?.systems ?? [])
const stageTracks = computed(() => st.value?.tracks ?? [])
const stageReady = computed(() => !!st.value?.ready)
const stageAt = computed(() => ({
  system: new Map(stageSystems.value.map((s, i) => [s.system, i])),
  track: new Map(stageTracks.value.map((t, i) => [t.track_id, i])),
}))
const cell = (cube, s, t, m) => cube?.[stageAt.value.system.get(s)]?.[stageAt.value.track.get(t)]?.[metricAt.get(m)] ?? NaN
const pctAt = (s, t, m) => cell(st.value?.pct, s, t, m)   // 百分位 0–1
const rawAt = (s, t, m) => cell(st.value?.raw, s, t, m)   // dB
const pctColor = computed(() => {
  const sc = d3.scaleSequential(d3.interpolateRgbBasis(dark.value ? SEQ_DARK : SEQ_LIGHT)).domain([0, 1]).clamp(true)
  return v => sc(v)
})

// 圖 2：指標錨點圖。每個系統在人聲上四個指標的中位數。
const anchorX = ref('SIR')
const anchorY = ref('SAR')
const anchorPoints = computed(() => st.value?.anchor ?? [])

// 圖 6：分群熱圖。分群結果記著它是哪個指標算的，熱圖的格子跟著它走。
const clusterK = ref(3)
const clusterMetric = computed(() => cl.value?.metric ?? metric.value)
const sliceValue = (s, t) => pctAt(s, t, clusterMetric.value)
const sliceRaw = (s, t) => rawAt(s, t, clusterMetric.value)
const fetchCluster = latest(api.cluster)
async function refreshCluster() {
  if (!stageReady.value) { cl.value = null; return }
  // 類別用「目前畫面上的列與欄」所屬的那一組，不用控制列的即時值：
  // 類別剛改、新的列欄還沒回來時，分群的欄順序才不會和熱圖對不上
  const query = { metric: metric.value, ...st.value.scope }
  const r = await call(() => fetchCluster(query))
  if (r) cl.value = { ...r, metric: query.metric }
}
watch(metric, refreshCluster)

// 圖 7–8：分割樹。樹的形狀存在前端：每個節點記著它在三個維度上的索引清單，
// 摘要（未解釋比例、各維度的模型值與偏差）由後端對那一塊子張量算出。
const tree = shallowRef(null)
const treeTick = ref(0)
const focusId = ref(-1)
const compareIds = ref([])
const splitMode = ref('auto')   // 'auto' | '0' 系統 | '1' 曲目 | '2' 指標
const splitK = ref(3)
const splitting = ref(false)
const linkHeatmap = ref(true)
let nodeSeq = 0
let initialSplit = q.get('p') || ''

const makeNode = (idx, summary, parent = null, label = '全部資料') =>
  ({ id: nodeSeq++, parent, label, idx, ...summary, children: [], splitMode: null, rec: null })
function attachChildren(node, result) {
  node.splitMode = result.mode
  node.rec = result.reductions          // [{ mode, reduction }]：三個維度各自的誤差降幅
  node.children = result.children.map((c, i) => makeNode(c.idx, c.summary, node, `${MODE_NAMES[result.mode]}第 ${i + 1} 群`))
}
function unsplit(node) { node.children = []; node.splitMode = null; node.rec = null }
function flatten(root) {
  const out = []
  const walk = (n, depth) => { out.push({ node: n, depth }); n.children.forEach(c => walk(c, depth + 1)) }
  if (root) walk(root, 0)
  return out
}

// 類別改變 → 列與欄改變 → 樹要重建。三件事（列欄、根節點、網址指定的第一次分割）一起取回再一起換上。
const fetchStage = latest(async query => {
  const stage = await api.stage(query)
  if (!stage.ready) return { stage, root: null, scope: query }
  const full = [stage.systems.length, stage.tracks.length, stage.metrics.length].map(range)
  const root = makeNode(full, await api.summary({ ...query, idx: full }))
  root.scope = query
  // 網址參數 p=<維度><群數>（例如 p=03 = 沿系統切 3 群）：還原根節點的第一次分割
  const m = /^([012])([234])$/.exec(initialSplit)
  if (m) {
    const result = await api.split({ ...query, idx: full, mode: +m[1], k: +m[2] })
    if (result.ok) attachChildren(root, result)
  }
  return { stage, root, scope: query }
})
async function refreshStage(strict = false) {
  const r = await call(() => fetchStage(scope()), strict)
  if (!r) return
  st.value = { ...r.stage, scope: r.scope }
  cl.value = null                        // 舊的分群是照舊的欄順序算的
  tree.value = r.root
  focusId.value = r.root ? r.root.id : -1
  compareIds.value = !r.root ? [] : r.root.children.length ? r.root.children.slice(0, 3).map(c => c.id) : [r.root.id]
  if (r.root) initialSplit = ''          // 只在第一次建樹時套用，之後切換類別不再重放
  treeTick.value++
  refreshCluster()
}
watch(cats, () => { if (meta.value) refreshStage() })

onMounted(async () => {
  try {
    meta.value = await api.meta()
    if (selectedTrack.value && !data.value.trackInfo.has(selectedTrack.value)) selectedTrack.value = ''
    await Promise.all([refreshOverview(true), refreshStage(true)])
  } catch (e) {
    error.value = describe(e)
  } finally {
    loading.value = false
  }
})

const flatNodes = computed(() => { treeTick.value; return flatten(tree.value) })
const nodeById = computed(() => new Map(flatNodes.value.map(f => [f.node.id, f.node])))
const focusNode = computed(() => nodeById.value.get(focusId.value) || null)
const sizesText = n => n.idx.map((ix, m) => `${ix.length} ${MODE_UNITS[m]}`).join(' × ')
const treeCards = computed(() => flatNodes.value.map(({ node, depth }) => {
  // 反向連結：這一塊包含哪些已選取的系統 / 曲目
  let note = ''
  if (node.parent) {
    // 只在這一塊「沒有涵蓋全部」的維度上標示，否則每張卡片都會寫同樣的字
    const root = tree.value
    const inSys = node.idx[0].length < root.idx[0].length ? node.idx[0].filter(i => selected.value.has(stageSystems.value[i].system)).length : 0
    const inTrack = node.idx[1].length < root.idx[1].length && selectedTrack.value && node.idx[1].some(i => stageTracks.value[i].track_id === selectedTrack.value)
    const parts = []
    if (inSys) parts.push(`${inSys} 個選取系統`)
    if (inTrack) parts.push('選取曲目')
    if (parts.length) note = '含 ' + parts.join('、')
  }
  return {
    id: node.id, parentId: node.parent ? node.parent.id : null, depth, label: node.label, sizes: sizesText(node),
    unexplained: node.unexplained, note,
    splitLabel: node.splitMode !== null ? `依${MODE_NAMES[node.splitMode]}分成 ${node.children.length} 群` : '',
  }
}))
const tags = computed(() => new Map(compareIds.value.map((id, i) => [id, 'ABC'[i]])))

function pickNode(id) {
  focusId.value = id
  const cur = compareIds.value
  if (cur.includes(id)) { if (cur.length > 1) compareIds.value = cur.filter(x => x !== id) }
  else compareIds.value = [...cur, id].slice(-3)
}
async function doSplit() {
  const node = focusNode.value
  const root = tree.value
  if (!node || node.children.length || splitting.value) return
  splitting.value = true
  try {
    const mode = splitMode.value === 'auto' ? null : +splitMode.value
    const result = await call(() => api.split({ ...root.scope, idx: node.idx, mode, k: +splitK.value }))
    // 切不動（ok 為假）就不改樹；等待期間樹被重建或這個節點已被切開時，也丟棄這次結果
    if (!result?.ok || tree.value !== root || node.children.length) return
    attachChildren(node, result)
    compareIds.value = node.children.slice(0, 3).map(c => c.id)
    treeTick.value++
  } finally {
    splitting.value = false
  }
}
function undoSplit() {
  const node = focusNode.value
  if (!node) return
  const target = node.children.length ? node : node.parent
  if (!target) return
  unsplit(target)
  focusId.value = target.id
  compareIds.value = [target.id]
  treeTick.value++
}
const splitReadout = computed(() => {
  treeTick.value                        // 分割後節點物件不變，要靠這個才會重算
  const node = focusNode.value
  const src = node?.rec ? node : node?.parent?.rec ? node.parent : null
  if (!src) return ''
  return src.rec.map(r => `依${MODE_NAMES[r.mode]} −${(100 * r.reduction).toFixed(0)}%`).join('、')
})

// 圖 8：選取區塊在三個維度上的摘要
//   model  = 摘要對該元素的平均重建值，單位與資料相同（百分位 0–1）
//   q1/med/q3 = 該元素所有格子「原始 − 重建」的四分位數
const modeKey = (m, i) => (m === 0 ? stageSystems.value[i].system : m === 1 ? stageTracks.value[i].track_id : METRIC_KEYS[i])
const panels = computed(() => {
  treeTick.value
  return compareIds.value.map(id => nodeById.value.get(id)).filter(Boolean).map(node => ({
    tag: tags.value.get(node.id),
    label: node.parent ? `${node.label} · ${node.idx[node.parent.splitMode].length} ${MODE_UNITS[node.parent.splitMode]}` : node.label,
    modes: node.modes.map((s, m) => new Map(s.index.map((i, j) => [modeKey(m, i), { index: i, model: s.model[j], q1: s.q1[j], med: s.med[j], q3: s.q3[j], absDev: s.absDev[j] }]))),
  }))
})
const patternModes = computed(() => {
  const has = (m, key) => panels.value.some(p => p.modes[m].has(key))
  return [
    { name: '系統', rows: stageSystems.value.filter(s => has(0, s.system)).map(s => ({ key: s.system, label: s.system, category: s.category })) },
    { name: '曲目', rows: stageTracks.value.filter(t => has(1, t.track_id)).map(t => ({ key: t.track_id, label: `${t.artist} – ${t.title}` })) },
    { name: '指標', rows: METRICS.filter(m => has(2, m.key)).map(m => ({ key: m.key, label: `${m.key}　${m.desc.split('：')[0]}` })) },
  ]
})

// 連結：分割樹 → 圖 3 曲目熱圖。找離焦點節點最近的「依曲目分割」，把曲目依那次分群排列。
const linkedTrackGroups = computed(() => {
  treeTick.value
  if (!linkHeatmap.value) return null
  let n = focusNode.value
  while (n && n.splitMode !== 1) n = n.parent
  if (!n) return null
  return n.children.map(c => ({ label: c.label, ids: new Set(c.idx[1].map(i => stageTracks.value[i].track_id)) }))
})
const heatmapLayout = computed(() => {
  const groups = linkedTrackGroups.value
  if (!groups) return { tracks: tracksSorted.value, groups: [] }
  const tracks = [], marks = []
  for (const g of groups) {
    const members = tracksSorted.value.filter(t => g.ids.has(t.track_id))
    if (!members.length) continue
    marks.push({ start: tracks.length, size: members.length, label: g.label })
    tracks.push(...members)
  }
  const rest = tracksSorted.value.filter(t => !groups.some(g => g.ids.has(t.track_id)))
  if (rest.length) { marks.push({ start: tracks.length, size: rest.length, label: '不在此分割內' }); tracks.push(...rest) }
  return { tracks, groups: marks }
})
// 代表曲：節點內摘要值位於中位數的那一首（由後端選出）
function jumpToRepresentative() {
  const node = focusNode.value
  if (!node) return
  selectedTrack.value = stageTracks.value[node.representativeTrack].track_id
}

// 網址同步（放在分割樹之後，因為要讀樹的狀態）
watch([metric, target, cats, selected, selectedTrack, () => treeTick.value], () => {
  const p = new URLSearchParams()
  if (metric.value !== 'SDR') p.set('m', metric.value)
  if (target.value !== 'vocals') p.set('s', target.value)
  if (cats.value.size !== CATEGORIES.length) p.set('c', [...cats.value].join(','))
  if (selected.value.size) p.set('sel', [...selected.value].join(','))
  if (selectedTrack.value) p.set('t', selectedTrack.value)
  const root = tree.value
  if (root && root.splitMode !== null) p.set('p', `${root.splitMode}${root.children.length}`)
  history.replaceState(null, '', p.size ? `?${p}` : location.pathname)
})

// ---------- 操作 ----------
function toggleSelect(system) {
  const next = new Set(selected.value)
  next.has(system) ? next.delete(system) : next.add(system)
  selected.value = next
}
function selectTrack(id) { selectedTrack.value = selectedTrack.value === id ? '' : id }
function clearSelection() { selected.value = new Set(); selectedTrack.value = '' }
const metricInfo = computed(() => METRICS.find(m => m.key === viewMetric.value))
const targetInfo = computed(() => TARGETS.find(t => t.key === viewTarget.value))
const fmt = v => (isNum(v) ? v.toFixed(2) : '–')
</script>

<template>
  <main>
    <header>
      <h1>從連動視圖到張量分割：用 TPFlow 的方法理解 SiSEC 2018 音樂分離評測</h1>
      <p>2018 年的 Signal Separation Evaluation Campaign 讓 31 個音樂分離系統在同樣 50 首歌上把人聲、鼓、貝斯、其他樂器拆出來，並用 BSS Eval 的四個指標逐秒評分。這個頁面分四個階段：從 HW2 的連動視圖出發，每一階段解決前一階段遇到的問題，最後走到 TPFlow 論文的張量分割。</p>
      <p class="meta">1151VIS 期末專案（延伸自 HW2）· Vue 3 + D3.js v7 · 資料：<a href="https://github.com/sigsep/sigsep-mus-2018">sigsep-mus-2018</a>（Stöter, Liutkus &amp; Ito, LVA/ICA 2018）· 方法：<a href="https://ieeexplore.ieee.org/document/8440840">TPFlow</a>（Liu, Xu &amp; Ren, IEEE TVCG 2019）</p>
      <nav class="stage-nav" aria-label="階段">
        <a href="#stage-1">1　連動視圖</a><a href="#stage-2">2　全部並排</a><a href="#stage-3">3　單片分群</a><a href="#stage-4">4　張量分割</a>
      </nav>
    </header>

    <p v-if="loading" class="status">資料載入中…</p>
    <p v-else-if="error" class="error">{{ error }}</p>
    <template v-else>
      <!-- ================= 階段 1 ================= -->
      <section id="stage-1" class="stage">
        <h2 class="stage-title"><span class="stage-no">階段 1</span>HW2 的做法：連動視圖，一次看一片</h2>
        <p class="stage-lead">先選一個指標和一個 stem，四張圖同步顯示那一片資料。這是探索多維資料最常見的做法，也是 TPFlow 論文開頭描述的做法。</p>
      </section>

      <ControlBar v-model:metric="metric" v-model:target="target" v-model:cats="cats"
        :selected-count="selected.size" :selected-track="selectedTrackInfo ? selectedTrackInfo.title : ''" @clear="clearSelection" />
      <p v-if="apiError" class="error" role="alert">{{ apiError }}</p>
      <div v-if="busy" class="busy" role="status">計算中…</div>

      <div class="grid-2">
        <figure>
          <h2>圖 1　排行榜 <span class="hint">{{ metricInfo.name }} 中位數 · 點欄名切換 stem，點列選取系統</span></h2>
          <p class="desc">列是系統，欄是五個 stem，格子是該系統在 50 首歌上 {{ metricInfo.name }} 的中位數（dB），顏色越深越高。依目前 stem（{{ targetInfo.name }}）排序。</p>
          <Leaderboard :rows="leaderboardRows" :target="viewTarget" :metric="viewMetric" :selected="selected" :color="color" :text-on="textOn"
            @select="toggleSelect" @set-target="target = $event" />
        </figure>
        <div>
          <figure>
            <h2>四個指標各在量什麼</h2>
            <p class="desc">BSS Eval 把系統估出的聲音拆成「目標」加上三種錯誤，四個指標都是目標對錯誤的能量比（dB），越高越好。</p>
            <ul class="glossary">
              <li v-for="m in METRICS" :key="m.key"><strong>{{ m.key }}</strong>　{{ m.desc }}</li>
            </ul>
            <p class="desc">兩個行為已知的參考點（灰色的 Oracle 類別）：<strong>MIX</strong> 直接把混音當答案，完全沒分離；<strong>IBM / IRM / MWF</strong> 用正確答案算出理想遮罩，是方法的上界。看它們在圖 2 落在哪裡，就能反推每個指標在懲罰什麼。</p>
          </figure>
        </div>
      </div>

      <figure>
        <h2>圖 2　指標錨點圖 <span class="hint">人聲 · 每個系統一個點 · 灰色為 Oracle 與 MIX</span></h2>
        <div class="view-tools">
          <span class="control-label">橫軸</span>
          <div class="seg"><button v-for="m in METRICS" :key="'x' + m.key" :class="{ on: anchorX === m.key }" @click="anchorX = m.key">{{ m.key }}</button></div>
          <span class="control-label">縱軸</span>
          <div class="seg"><button v-for="m in METRICS" :key="'y' + m.key" :class="{ on: anchorY === m.key }" @click="anchorY = m.key">{{ m.key }}</button></div>
        </div>
        <p class="desc">預設看 SIR 對 SAR。MIX 沒做任何加工，所以 SAR（瑕疵）最好、SIR（漏音）幾乎最差；理想二元遮罩 IBM 切得最狠，SIR 最高但 SAR 反而不如 MIX。SAR 高不代表分得好。</p>
        <MetricAnchor :points="anchorPoints" :x-metric="anchorX" :y-metric="anchorY" :selected="selected" @select="toggleSelect" />
      </figure>

      <figure>
        <h2>圖 3　曲目熱圖 <span class="hint">系統 × 曲目 · {{ targetInfo.name }} · {{ metricInfo.name }} · 點曲目看逐秒</span></h2>
        <p class="desc" v-if="heatmapLayout.groups.length">曲目目前<strong>依階段 4 分割樹的分群</strong>排列（群內由難到易），可以直接檢查演算法找到的群在原始分數上看不看得出來。在階段 4 取消勾選即可恢復由難到易。</p>
        <p class="desc" v-else>列依排行、欄依「難度」排序（非 oracle 系統在該曲的中位數）。整欄都淺色的歌對所有系統都難；一列整體偏深的系統全面較強。</p>
        <TrackHeatmap :systems="ranking" :tracks="heatmapLayout.tracks" :groups="heatmapLayout.groups" :value="valueAt" :selected="selected" :selected-track="selectedTrack"
          :color="color" :metric="viewMetric" @select="toggleSelect" @select-track="selectTrack" />
      </figure>

      <figure>
        <h2>圖 4　逐秒時間線
          <span class="hint" v-if="selectedTrackInfo">{{ selectedTrackInfo.artist }} – {{ selectedTrackInfo.title }} · {{ targetInfo.name }} · {{ metricInfo.name }} · 拖曳放大，雙擊還原</span>
          <span class="hint" v-else>在圖 3 點一首歌</span>
        </h2>
        <p class="desc">畫出{{ selected.size ? '已選取的系統' : '排行前 5 的系統' }}在這首歌上每一秒的分數。線的顏色是系統類別，線尾標系統名。</p>
        <Timeline v-if="selectedTrack && frames" :frames="frames" :systems="timelineSystems" :target="viewTarget" :metric="viewMetric"
          :track-label="selectedTrackInfo ? selectedTrackInfo.title : ''" />
        <p v-else-if="selectedTrack" class="status">載入逐秒資料中…</p>
        <p v-else class="placeholder-text">尚未選取曲目。</p>
      </figure>

      <details class="panel">
        <summary>HW2 的另外兩張圖：方法地圖（MDS）與優勢圖（Hasse diagram）</summary>
        <figure>
          <h2>圖 A　方法地圖 <span class="hint">MDS · 連線 = 共同作者</span></h2>
          <p class="desc">每個系統一個點，位置由 50 首歌分數剖面的相關係數經 MDS 投影而來：靠近 = 在同樣的歌上同樣好或同樣壞。連線表示兩個系統有共同作者。</p>
          <MethodMap :points="mapPoints" :edges="authorEdges" :selected="selected" :metric="viewMetric" @select="toggleSelect" />
        </figure>
        <figure>
          <h2>圖 B　優勢圖 <span class="hint">誰顯著贏誰 · {{ targetInfo.name }} · {{ metricInfo.name }}</span></h2>
          <p class="desc">對每一對系統，用 50 首歌的配對分數做 Wilcoxon signed-rank 檢定。「A 顯著優於 B」畫成由左往右的邊，再去掉可由遞移推得的邊（{{ dominance.allEdges }} 對顯著關係化簡為 {{ dominance.edges.length }} 條邊）。</p>
          <DominanceGraph :nodes="ranking" :edges="dominance.edges" :layers="dominance.layers" :win="dominance.win"
            :selected="selected" :metric="viewMetric" :alpha="ALPHA" :dark="dark" @select="toggleSelect" />
        </figure>
      </details>

      <p class="problem"><strong>遇到的問題</strong>　4 個指標 × 5 個分離目標 = 20 片，每一片都要手動切換才看得到。切到下一片時，上一片只剩記憶；也不知道哪幾片值得看。TPFlow 論文稱這個過程「冗長又乏味」。</p>

      <!-- ================= 階段 2 ================= -->
      <section id="stage-2" class="stage">
        <h2 class="stage-title"><span class="stage-no">階段 2</span>全部並排：不靠記憶比較</h2>
        <p class="stage-lead">課堂第 6 週的原則「Eyes beat memory」：並排比較比切換後靠記憶比較容易。從這裡開始固定看人聲，因為只有人聲涵蓋全部 31 個系統。</p>
      </section>
      <template v-if="stageReady">
        <figure>
          <h2>圖 5　四個指標並排 <span class="hint">人聲 · 系統 × 曲目 · small multiples</span></h2>
          <p class="desc">四張熱圖的列（系統，依人聲 SDR 排行）和欄（曲目，由難到易）完全相同。四個指標的 dB 尺度不同，所以顏色改用百分位：每個指標各自對全部分數排名，越深代表在該指標上越高。</p>
          <SmallMultiples :systems="stageSystems" :tracks="stageTracks" :metrics="METRIC_KEYS" :value="pctAt" :raw="rawAt" :color="pctColor"
            :selected="selected" :selected-track="selectedTrack" @select="toggleSelect" @select-track="selectTrack" />
        </figure>
        <p class="problem"><strong>遇到的問題</strong>　不用靠記憶了，也看得出 SDR 和 SIR 很像、SAR 和 ISR 是另一種樣子。但「哪些歌是一類」「哪些系統是一類」只能用眼睛猜，四張圖之間的差異也說不出一個具體的結構。</p>

        <!-- ================= 階段 3 ================= -->
        <section id="stage-3" class="stage">
          <h2 class="stage-title"><span class="stage-no">階段 3</span>單片分群：讓演算法重排一張熱圖</h2>
          <p class="stage-lead">課堂第 7 週的 cluster heatmap：對一片熱圖的欄做階層式分群，依分群結果重排，並把樹狀圖畫在上方。</p>
        </section>
        <figure>
          <h2>圖 6　分群熱圖 <span class="hint">人聲 · {{ clusterMetric }} · 曲目依階層式分群重排</span></h2>
          <div class="view-tools">
            <span class="control-label">切成幾群</span>
            <div class="seg"><button v-for="k in [2, 3, 4, 5]" :key="k" :class="{ on: clusterK === k }" @click="clusterK = k">{{ k }}</button></div>
            <span class="view-hint">用最上方控制列的「指標」換一片，分群結果會跟著變</span>
          </div>
          <p class="desc">每首歌的特徵是它那一欄（各系統在這首歌上的百分位），距離用歐氏距離、合併用 average linkage。</p>
          <ClusterHeatmap :systems="stageSystems" :tracks="stageTracks" :value="sliceValue" :raw="sliceRaw" :k="clusterK" :color="pctColor" :metric="clusterMetric" :clustering="cl"
            :selected="selected" :selected-track="selectedTrack" @select="toggleSelect" @select-track="selectTrack" />
        </figure>
        <p class="problem"><strong>遇到的問題</strong>　看得到群了，但一次只能處理一片（兩個維度）。換一個指標，分群就不一樣；四個指標合起來歌曲該怎麼分、系統該不該也分，這個方法回答不了。TPFlow 論文在相關研究一節指出同樣的限制。</p>

        <!-- ================= 階段 4 ================= -->
        <section id="stage-4" class="stage">
          <h2 class="stage-title"><span class="stage-no">階段 4</span>TPFlow：把所有維度當成一個張量來分割</h2>
          <p class="stage-lead">把人聲的分數排成「系統 × 曲目 × 指標」的張量。先用每個維度一組長條當作整塊資料的摘要（rank-one 近似）；摘要不夠忠實時，沿一個維度自動分群，每一群各自再做摘要，可以一直往下切。</p>
        </section>
        <figure>
          <h2>圖 7　分割樹 <span class="hint">點卡片選取（最多三塊，標為 A B C）· 粗框為目前操作的節點</span></h2>
          <div class="view-tools">
            <span class="control-label">沿哪個維度切</span>
            <div class="seg">
              <button :class="{ on: splitMode === 'auto' }" @click="splitMode = 'auto'">自動推薦</button>
              <button v-for="(n, i) in MODE_NAMES" :key="n" :class="{ on: splitMode === String(i) }" @click="splitMode = String(i)">{{ n }}</button>
            </div>
            <span class="control-label">幾群</span>
            <div class="seg"><button v-for="k in [2, 3, 4]" :key="k" :class="{ on: splitK === k }" @click="splitK = k">{{ k }}</button></div>
            <button @click="doSplit" :disabled="!focusNode || focusNode.children.length > 0 || splitting">分割選取的節點</button>
            <button class="secondary" @click="undoSplit" :disabled="!focusNode || (!focusNode.children.length && !focusNode.parent)">復原</button>
          </div>
          <p class="desc">每張卡片是一塊資料，長條是摘要沒解釋到的比例（殘差平方和 ÷ 總平方和），越短代表那組長條越能代表這塊資料。<span v-if="splitReadout">這次分割若改沿其他維度，誤差的降幅分別是：{{ splitReadout }}。</span></p>
          <p class="desc">注意：「自動推薦」選的是分割後誤差最小的維度，但它會偏向元素最少的維度。指標只有 4 個，切開後每一群都各自擁有一整組系統和曲目的長條，等於多了很多自由度，誤差自然降得多。所以上面列出三個維度的降幅讓你自己判斷。</p>
          <PartitionTree :nodes="treeCards" :tags="tags" :focus-id="focusId" @pick="pickNode" />
        </figure>

        <figure>
          <h2>圖 8　區塊模式圖 <span class="hint">每個維度一組長條 · 選取的區塊並排</span></h2>
          <div class="view-tools">
            <label class="check"><input type="checkbox" v-model="linkHeatmap" /> 圖 3 的曲目依分割樹的分群排列</label>
            <button class="secondary" @click="jumpToRepresentative" :disabled="!focusNode">在圖 4 看這一塊的代表曲（摘要值居中的那首）</button>
          </div>
          <p class="desc">長條是摘要對該列的平均重建值（百分位，0 到 100）。細鬚線是原始資料相對於摘要的偏差（第一到第三四分位，圓點為中位數）：鬚線短且靠近長條末端，表示摘要可信；鬚線長，表示這一塊還混著不同的模式，值得再切。系統的長條顏色是系統類別。點系統或曲目的列會選取它，其他圖同步高亮。</p>
          <PatternBars :panels="panels" :modes="patternModes" :selected="selected" :selected-track="selectedTrack"
            @select="toggleSelect" @select-track="selectTrack" />
        </figure>
      </template>
      <p v-else class="placeholder-text">階段 2 到 4 至少需要 3 個系統，請在控制列多開幾個類別。</p>

      <section class="panel">
        <h2>可以試試看</h2>
        <ul class="tips">
          <li><strong>圖 2 換軸</strong>：把橫軸換成 SDR、縱軸換成 ISR，看 MIX 落在哪裡。</li>
          <li><strong>圖 7 沿指標切 2 群</strong>：SDR 和 SIR 一群、SAR 和 ISR 一群，和圖 5 用眼睛看到的一致。</li>
          <li><strong>圖 7 沿曲目切 3 群</strong>：誤差只降約一成，分出來的是「較易」「較難」和兩首沒有人聲的純演奏曲。也就是說，這 50 首歌主要是由難到易的連續變化，沒有明顯的類型。回圖 3 可以看分群後的熱圖。</li>
          <li><strong>圖 7 沿系統切 3 群</strong>：誤差降約三成，比沿曲目切有效。除了強、弱兩群，還會分出很小的一群（MIX、HPLP、REP1）：看它們在「指標維度」的長條，SAR 和 ISR 高、SDR 和 SIR 低，也就是幾乎沒動混音的系統。</li>
          <li><strong>關掉 Oracle</strong>：階段 2 到 4 會用剩下的系統重算，分割樹重置。</li>
          <li><strong>選幾個系統再看圖 7</strong>：卡片會標出每一塊包含幾個選取的系統。</li>
        </ul>
      </section>

      <section class="panel">
        <h2>背後的方法（摘要）</h2>
        <ul class="math">
          <li><strong>指標</strong>：BSS Eval 把估計出的 stem 拆成 目標 + 空間失真 + 干擾 + 瑕疵 四個分量，SDR、ISR、SIR、SAR 分別是目標對（全部錯誤 / 空間失真 / 干擾 / 瑕疵）的能量比，單位 dB。</li>
          <li><strong>彙整</strong>：每首歌對逐秒分數取中位數，系統排名再對 50 首歌取中位數（與 SiSEC 官方一致）。</li>
          <li><strong>百分位</strong>：每個指標各自對全部系統 × 50 首歌的分數排名，值 = (名次 − 0.5) / n。TPFlow 處理非負的計數資料，dB 分數有負值且各指標尺度不同，轉成百分位後才能放進同一個非負張量。</li>
          <li><strong>rank-one 摘要</strong>：X ≈ λ · a ⊗ b ⊗ c，a、b、c 分別是系統、曲目、指標維度的非負單位向量，用交替最小平方法求解。誤差 = 殘差平方和。</li>
          <li><strong>分割</strong>（TPFlow 第 3.2 節）：先做連續 rank-one 分解取前 3 組向量，要切的維度上每個元素得到一個 3 維特徵，用 k-means 分群，每群各自重做 rank-one 摘要。</li>
          <li><strong>與論文不同之處</strong>：偏差用絕對差而非相對差（百分位接近 0 時相對差會失真）；分群用的特徵乘上了各組的強度 λ，讓較強的模式影響較大；k-means 用確定性的初始化，重新整理後結果相同；沒有實作 OPTICS、地圖與流向圖。</li>
        </ul>
      </section>

      <details class="panel">
        <summary>資料表：31 個系統的屬性（作者、機構、程式）</summary>
        <table>
          <thead><tr><th>系統</th><th>類別</th><th>blind</th><th>額外資料</th><th>{{ metricInfo.name }} 中位數</th><th>作者</th><th>機構</th><th>程式</th></tr></thead>
          <tbody>
            <tr v-for="r in leaderboardRows" :key="r.system" :class="{ selected: selected.has(r.system) }" @click="toggleSelect(r.system)">
              <td><span class="swatch" :style="{ background: CATEGORY[r.category].color }"></span>{{ r.system }}</td>
              <td>{{ CATEGORY[r.category].short }}</td>
              <td>{{ data.systemInfo.get(r.system).is_blind }}</td>
              <td>{{ data.systemInfo.get(r.system).extra_data }}</td>
              <td class="num">{{ fmt(r.median) }}</td>
              <td class="small">{{ data.systemInfo.get(r.system).authors }}</td>
              <td class="small">{{ data.systemInfo.get(r.system).affiliation }}</td>
              <td class="small"><a v-if="data.systemInfo.get(r.system).code" :href="data.systemInfo.get(r.system).code" target="_blank" rel="noopener">連結</a></td>
            </tr>
          </tbody>
        </table>
      </details>
    </template>

    <footer>
      執行方式：<code>npm install</code> 之後同時開 <code>npm run api</code>（Python 計算後端）與 <code>npm run dev</code>。資料由 <code>python3 -I prepare_data.py &lt;sigsep-mus-2018 路徑&gt;</code> 彙整到 <code>public/data/</code>。
      <code>npm run check</code> 驗證統計與張量函式。
    </footer>

    <div v-if="tip.show" class="tooltip" :style="{ left: tip.x + 'px', top: tip.y + 'px' }" v-html="tip.html"></div>
  </main>
</template>
