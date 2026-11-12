// 分割樹：TPFlow 的漸進式分割流程。每個節點是基底張量的一塊子張量，附帶它的 rank-one 摘要。
import { subTensor, rankOne, residual, recommendPartition } from './tensor.js'

export const MODE_NAMES = ['系統', '曲目', '指標']
export const MODE_UNITS = ['個系統', '首歌', '個指標']

let seq = 0

// idx：每個 mode 在基底張量上的索引陣列
export function makeNode(base, idx, parent = null, label = '全部資料') {
  let T = base
  idx.forEach((ix, m) => { T = subTensor(T, m, ix) })
  const fit = rankOne(T)
  let total = 0
  for (let i = 0; i < T.data.length; i++) total += T.data[i] * T.data[i]
  return {
    id: seq++, parent, label, idx, T, fit, total,
    unexplained: total > 0 ? fit.cost / total : 0,   // 摘要沒解釋到的比例（殘差平方和 / 總平方和）
    children: [], splitMode: null, rec: null,
  }
}

// mode：0 / 1 / 2 或 'auto'。成功回傳 true。
export function splitNode(base, node, mode, k) {
  const rec = recommendPartition(node.T, k)
  const chosen = mode === 'auto' ? rec[0] : rec.find(r => r.mode === mode)
  if (!chosen || chosen.groups.length < 2) return false
  node.splitMode = chosen.mode
  node.rec = rec.map(r => ({ mode: r.mode, cost: r.cost, reduction: node.fit.cost > 0 ? 1 - r.cost / node.fit.cost : 0 }))
  node.children = chosen.groups.map((g, i) => {
    const idx = node.idx.map((ix, m) => (m === chosen.mode ? g.map(j => ix[j]) : ix))
    return makeNode(base, idx, node, `${MODE_NAMES[chosen.mode]}第 ${i + 1} 群`)
  })
  return true
}

export function unsplit(node) { node.children = []; node.splitMode = null; node.rec = null }

export function flatten(root) {
  const out = []
  const walk = (n, depth) => { out.push({ node: n, depth }); n.children.forEach(c => walk(c, depth + 1)) }
  if (root) walk(root, 0)
  return out
}

const quantile = (sorted, p) => {
  if (!sorted.length) return NaN
  const h = (sorted.length - 1) * p, lo = Math.floor(h), hi = Math.ceil(h)
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (h - lo)
}

// 節點在某個 mode 上的摘要：每個元素一筆
//   model  = 摘要對該元素的平均重建值（λ · v[j] · 其他 mode 的向量平均），單位與資料相同（百分位 0–1）
//   q1/med/q3 = 該元素所有格子「原始 − 重建」的四分位數（論文 4.2.3 的偏差，這裡用絕對差而非相對差）
//   absDev = 平均絕對偏差
export function modeSummary(node, m) {
  const { T, fit } = node
  const shape = T.shape
  const R = residual(T, fit.lambda, fit.vectors)
  const stride = shape.slice(m + 1).reduce((a, b) => a * b, 1)
  const buckets = Array.from({ length: shape[m] }, () => [])
  for (let f = 0; f < R.data.length; f++) buckets[Math.floor(f / stride) % shape[m]].push(R.data[f])
  let others = fit.lambda
  fit.vectors.forEach((v, k) => { if (k !== m) others *= v.reduce((a, b) => a + b, 0) / v.length })
  return buckets.map((b, j) => {
    b.sort((x, y) => x - y)
    return {
      index: node.idx[m][j],
      model: fit.vectors[m][j] * others,
      q1: quantile(b, 0.25), med: quantile(b, 0.5), q3: quantile(b, 0.75),
      absDev: b.reduce((s, v) => s + Math.abs(v), 0) / b.length,
    }
  })
}

// 代表元素：節點內摘要值位於中位數的那一個（最「典型」的一首歌或一個系統），回傳基底索引。
// 不用「偏差最小」，因為分數趨近 0 的元素（例如沒有人聲的純演奏曲）偏差必然最小，卻最不典型。
export function representative(node, m) {
  const s = [...modeSummary(node, m)].sort((x, y) => x.model - y.model)
  return s[s.length >> 1].index
}
