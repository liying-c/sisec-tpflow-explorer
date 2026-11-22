// 用現有的 JS 演算法在真實資料上輸出基準檔，供 Python 版逐項比對。
// 推導方式照 src/App.vue 的 computed。用法：node tests/dump_golden.mjs
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import * as d3 from 'd3'
import { median, pearson, wilcoxon, classicalMds, transitiveReduction, layerByLongestPath, isNum } from '../src/stats.js'
import { makeTensor, percentileRanks, hclust } from '../src/tensor.js'
import { makeNode, splitNode, modeSummary, representative } from '../src/partition.js'
import { profile, authorSet } from '../src/data.js'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const read = (name, typed) => d3.csvParse(fs.readFileSync(path.join(root, 'public/data', name), 'utf8'), typed ? d3.autoType : undefined)
const systems = read('systems.csv', false)
const tracks = read('tracks.csv', true)
const scores = read('scores_track.csv', true)

const index = new Map()
for (const r of scores) {
  if (!index.has(r.system)) index.set(r.system, new Map())
  const byTarget = index.get(r.system)
  if (!byTarget.has(r.target)) byTarget.set(r.target, new Map())
  byTarget.get(r.target).set(r.track_id, r)
}
const trackInfo = new Map(tracks.map(t => [t.track_id, t]))
const trackIds = tracks.map(t => t.track_id)
const METRIC_KEYS = ['SDR', 'SIR', 'SAR', 'ISR']
const TARGET_KEYS = ['vocals', 'drums', 'bass', 'other', 'accompaniment']
const ALPHA = 0.05
const STAGE_TARGET = 'vocals'
const range = n => Array.from({ length: n }, (_, i) => i)
const sortDesc = (a, b) => (isNum(b.median) ? b.median : -1e9) - (isNum(a.median) ? a.median : -1e9)
const byDifficulty = (a, b) => (isNum(a.difficulty) ? a.difficulty : 1e9) - (isNum(b.difficulty) ? b.difficulty : 1e9)

function overview(visible, metric, target) {
  const profiles = new Map(visible.map(s => [s.system, profile(index, s.system, target, metric, trackIds)]))
  const medians = new Map([...profiles].map(([s, p]) => [s, median(p)]))
  const ranking = visible.map(s => ({ system: s.system, category: s.category, median: medians.get(s.system) })).sort(sortDesc)
  const leaderboard = ranking.map(r => ({
    ...r,
    values: Object.fromEntries(TARGET_KEYS.map(t => [t, median(profile(index, r.system, t, metric, trackIds))])),
  }))
  const vis = new Set(visible.map(s => s.system))
  const vals = scores.filter(r => vis.has(r.system) && isNum(r[metric])).map(r => r[metric]).sort(d3.ascending)
  const colorDomain = [d3.quantile(vals, 0.05) ?? 0, d3.quantile(vals, 0.99) ?? 10]

  let mdsXY = [], mdsDistances = []
  if (visible.length >= 3) {
    const dist = visible.map(a => visible.map(b => {
      if (a === b) return 0
      const r = pearson(profiles.get(a.system), profiles.get(b.system))
      return isNum(r) ? Math.sqrt(Math.max(0, 2 * (1 - r))) : 2
    }))
    mdsXY = classicalMds(dist)
    mdsDistances = mdsXY.map(p => mdsXY.map(q => Math.hypot(p[0] - q[0], p[1] - q[1])))
  }
  const sets = visible.map(s => ({ system: s.system, authors: authorSet(s.authors) }))
  const authorEdges = []
  for (let i = 0; i < sets.length; i++) for (let j = i + 1; j < sets.length; j++) {
    const shared = [...sets[i].authors].filter(a => sets[j].authors.has(a))
    if (shared.length) authorEdges.push({ a: sets[i].system, b: sets[j].system, shared: shared.map(n => n.replace(/\b\w/g, c => c.toUpperCase())) })
  }

  const sys = ranking.map(r => r.system)
  const win = (a, b) => {
    const pa = profiles.get(a), pb = profiles.get(b)
    let wins = 0, n = 0
    for (let i = 0; i < pa.length; i++) if (isNum(pa[i]) && isNum(pb[i])) { n++; if (pa[i] > pb[i]) wins++ }
    return { wins, n, p: wilcoxon(pa, pb).p }
  }
  const pairs = sys.map(a => sys.map(b => win(a, b)))
  const edges = []
  for (let i = 0; i < sys.length; i++) for (let j = i + 1; j < sys.length; j++) {
    const s = pairs[i][j]
    if (s.p < ALPHA && (s.n ? s.wins / s.n : NaN) > 0.5) edges.push([sys[i], sys[j]])
  }
  const reduced = transitiveReduction(sys, edges)
  const layers = layerByLongestPath(sys, reduced)

  const pool = visible.filter(s => s.category !== 'oracle')
  const use = pool.length ? pool : visible
  const tracksSorted = trackIds.map((t, k) => ({ ...trackInfo.get(t), difficulty: median(use.map(s => profiles.get(s.system)[k])) })).sort(byDifficulty)

  return {
    metric, target, visible: visible.map(s => s.system), ranking, leaderboard, colorDomain, tracksSorted,
    mdsXY, mdsDistances, authorEdges,
    dominance: {
      order: sys, edges: reduced, allEdges: edges.length, layers: Object.fromEntries(layers),
      wins: pairs.map(r => r.map(c => c.wins)), n: pairs.map(r => r.map(c => c.n)), p: pairs.map(r => r.map(c => c.p)),
    },
  }
}

// 百分位：對全部系統的人聲分數、每個指標各自排名（不受類別影響）
const pct = (() => {
  const rows = scores.filter(r => r.target === STAGE_TARGET)
  const out = new Map()
  const cells = rows.map(r => {
    if (!out.has(r.system)) out.set(r.system, new Map())
    const o = {}
    out.get(r.system).set(r.track_id, o)
    return o
  })
  for (const m of METRIC_KEYS) {
    const ok = rows.map((r, i) => i).filter(i => isNum(rows[i][m]))
    const pr = percentileRanks(ok.map(i => rows[i][m]))
    ok.forEach((i, j) => { cells[i][m] = pr[j] })
  }
  return out
})()
const pctAt = (s, t, m) => pct.get(s)?.get(t)?.[m] ?? NaN
const rawAt = (s, t, m) => { const v = index.get(s)?.get(STAGE_TARGET)?.get(t)?.[m]; return isNum(v) ? v : NaN }

function stage(visible) {
  const stageProfiles = new Map(visible.map(s => [s.system, profile(index, s.system, STAGE_TARGET, 'SDR', trackIds)]))
  const S = visible.map(s => ({ system: s.system, category: s.category, median: median(stageProfiles.get(s.system)) })).filter(s => isNum(s.median)).sort(sortDesc)
  const pool = S.filter(s => s.category !== 'oracle')
  const use = pool.length ? pool : S
  const Tr = trackIds.map((t, k) => ({ ...trackInfo.get(t), difficulty: median(use.map(s => stageProfiles.get(s.system)[k])) })).sort(byDifficulty)
  const anchor = visible.map(s => ({
    system: s.system, category: s.category,
    ...Object.fromEntries(METRIC_KEYS.map(m => [m, median(profile(index, s.system, STAGE_TARGET, m, trackIds))])),
  }))
  return {
    ready: S.length >= 3, systems: S, tracks: Tr, metrics: METRIC_KEYS, anchor,
    pct: S.map(s => Tr.map(t => METRIC_KEYS.map(m => pctAt(s.system, t.track_id, m)))),
    raw: S.map(s => Tr.map(t => METRIC_KEYS.map(m => rawAt(s.system, t.track_id, m)))),
  }
}

function cluster(st, metric) {
  const points = st.tracks.map(t => st.systems.map(s => {
    const v = pctAt(s.system, t.track_id, metric)
    return Number.isFinite(v) ? v : 0.5
  }))
  const h = hclust(points)
  return { order: h.order, merges: h.merges, labels: Object.fromEntries([2, 3, 4, 5].map(k => [k, h.cut(k)])) }
}

const summaryOf = node => ({
  idx: node.idx, lambda: node.fit.lambda, cost: node.fit.cost, unexplained: node.unexplained,
  modes: [0, 1, 2].map(m => modeSummary(node, m)), representativeTrack: representative(node, 1),
})
const splitOf = (T, node, mode, k) => {
  const ok = splitNode(T, node, mode, k)
  if (!ok) return { ok: false }
  return { ok: true, mode: node.splitMode, rec: node.rec, children: node.children.map(summaryOf) }
}

function partition(st) {
  const T = makeTensor([st.systems.length, st.tracks.length, METRIC_KEYS.length])
  let f = 0
  for (const row of st.pct) for (const cell of row) for (const v of cell) T.data[f++] = isNum(v) ? v : 0.5
  const fresh = () => makeNode(T, T.shape.map(range))
  const splits = []
  for (const mode of [0, 1, 2]) for (const k of [2, 3, 4]) splits.push({ mode, k, ...splitOf(T, fresh(), mode, k) })
  const auto = [2, 3, 4].map(k => ({ k, ...splitOf(T, fresh(), 'auto', k) }))
  // 第二層：沿系統切 3 群後，對第 1 個子塊沿指標切 2 群
  const top = fresh()
  splitNode(T, top, 0, 3)
  const second = { parentIdx: top.children[0].idx, mode: 2, k: 2, ...splitOf(T, top.children[0], 2, 2) }
  return { root: summaryOf(fresh()), splits, auto, second }
}

const GROUPS = {
  all: ['supervised', 'supervised+extra', 'blind', 'oracle'],
  'no-oracle': ['supervised', 'supervised+extra', 'blind'],
}
const outDir = path.join(root, 'backend/tests/golden')
fs.mkdirSync(outDir, { recursive: true })
for (const [name, cats] of Object.entries(GROUPS)) {
  const visible = systems.filter(s => cats.includes(s.category))
  const st = stage(visible)
  const out = {
    categories: cats,
    overview: [overview(visible, 'SDR', 'vocals'), overview(visible, 'SIR', 'drums')],
    stage: st,
    cluster: Object.fromEntries(METRIC_KEYS.map(m => [m, cluster(st, m)])),
    partition: partition(st),
  }
  // NaN → null（JSON.stringify 的預設行為），Float64Array → 一般陣列
  const json = JSON.stringify(out, (k, v) => (v instanceof Float64Array ? Array.from(v) : v))
  fs.writeFileSync(path.join(outDir, `${name}.json`), json)
  const p = out.partition
  const red = (m, k) => { const s = p.splits.find(x => x.mode === m && x.k === k); return s.rec.find(r => r.mode === m).reduction }
  console.log(`${name}: ${st.systems.length} 系統, 未解釋 ${(100 * p.root.unexplained).toFixed(1)}%, 指標k2 −${(100 * red(2, 2)).toFixed(0)}%, 系統k3 −${(100 * red(0, 3)).toFixed(0)}%, 曲目k3 −${(100 * red(1, 3)).toFixed(0)}%, ${(json.length / 1024).toFixed(0)} KB`)
}
