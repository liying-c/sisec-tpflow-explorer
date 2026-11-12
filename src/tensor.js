// 張量工具：TPFlow（Liu, Xu & Ren, IEEE TVCG 2019）第 3 節的 piecewise rank-one tensor decomposition。
// 全部純 JavaScript。張量以 { shape: [n0, n1, ...], data: Float64Array } 表示，row-major。
// 輸入必須是完整（無 NaN）的非負張量。

export function makeTensor(shape, fill = 0) {
  const size = shape.reduce((a, b) => a * b, 1)
  return { shape: [...shape], data: new Float64Array(size).fill(fill) }
}

const strides = shape => {
  const s = new Array(shape.length)
  let acc = 1
  for (let m = shape.length - 1; m >= 0; m--) { s[m] = acc; acc *= shape[m] }
  return s
}

// 走訪每一格：cb(flatIndex, idx[])
function forEachCell(shape, cb) {
  const idx = new Array(shape.length).fill(0)
  const size = shape.reduce((a, b) => a * b, 1)
  for (let f = 0; f < size; f++) {
    cb(f, idx)
    for (let m = shape.length - 1; m >= 0; m--) { if (++idx[m] < shape[m]) break; idx[m] = 0 }
  }
}

// 沿 mode 取出 indices 指定的切片，疊成子張量
export function subTensor(T, mode, indices) {
  const shape = [...T.shape]
  shape[mode] = indices.length
  const out = makeTensor(shape)
  const st = strides(T.shape)
  forEachCell(shape, (f, idx) => {
    let src = 0
    for (let m = 0; m < shape.length; m++) src += (m === mode ? indices[idx[m]] : idx[m]) * st[m]
    out.data[f] = T.data[src]
  })
  return out
}

// 百分位轉換：(名次 − 0.5) / n，同值取平均名次。回傳與輸入等長的陣列，值域 (0, 1)。
export function percentileRanks(values) {
  const n = values.length
  const order = values.map((v, i) => ({ v, i })).sort((a, b) => a.v - b.v)
  const out = new Array(n)
  for (let i = 0; i < n;) {
    let j = i
    while (j + 1 < n && order[j + 1].v === order[i].v) j++
    const r = (i + j + 2) / 2
    for (let k = i; k <= j; k++) out[order[k].i] = (r - 0.5) / n
    i = j + 1
  }
  return out
}

// ---------- rank-one 近似（交替最小平方法） ----------
// X ≈ λ · v0 ⊗ v1 ⊗ ...，各 v 為單位向量。nonneg = true 時把負值截為 0（論文對第一組 loading vectors 的限制）。
// 回傳 { lambda, vectors, cost }，cost = 殘差平方和（可加總，子張量的 cost 相加可與母張量比較）。
export function rankOne(T, { nonneg = true, iters = 200, tol = 1e-10 } = {}) {
  const { shape, data } = T
  const M = shape.length
  let vectors = shape.map(n => new Float64Array(n).fill(1 / Math.sqrt(n)))
  let lambda = 0
  for (let it = 0; it < iters; it++) {
    let change = 0
    for (let m = 0; m < M; m++) {
      const w = new Float64Array(shape[m])
      forEachCell(shape, (f, idx) => {
        let p = data[f]
        if (p === 0) return
        for (let k = 0; k < M; k++) if (k !== m) p *= vectors[k][idx[k]]
        w[idx[m]] += p
      })
      if (nonneg) for (let i = 0; i < w.length; i++) if (w[i] < 0) w[i] = 0
      let norm = 0
      for (let i = 0; i < w.length; i++) norm += w[i] * w[i]
      norm = Math.sqrt(norm)
      if (norm === 0) return { lambda: 0, vectors, cost: sumSquares(data) }
      for (let i = 0; i < w.length; i++) { w[i] /= norm; change += Math.abs(w[i] - vectors[m][i]) }
      vectors[m] = w
      lambda = norm
    }
    if (change < tol) break
  }
  return { lambda, vectors, cost: residualCost(T, lambda, vectors) }
}

const sumSquares = data => { let s = 0; for (let i = 0; i < data.length; i++) s += data[i] * data[i]; return s }

function residualCost(T, lambda, vectors) {
  let s = 0
  forEachCell(T.shape, (f, idx) => {
    let p = lambda
    for (let k = 0; k < idx.length; k++) p *= vectors[k][idx[k]]
    const d = T.data[f] - p
    s += d * d
  })
  return s
}

// 重建值與殘差（原始 − 重建），供偏差視覺化使用
export function residual(T, lambda, vectors) {
  const out = makeTensor(T.shape)
  forEachCell(T.shape, (f, idx) => {
    let p = lambda
    for (let k = 0; k < idx.length; k++) p *= vectors[k][idx[k]]
    out.data[f] = T.data[f] - p
  })
  return out
}

// 連續 rank-one 分解：第 1 組非負，之後對殘差再做 rank-one（不限制正負）。回傳 R 組 { lambda, vectors }。
export function successiveRankOne(T, R) {
  const comps = []
  let cur = T
  for (let r = 0; r < R; r++) {
    const c = rankOne(cur, { nonneg: r === 0 })
    if (c.lambda === 0) break
    comps.push(c)
    cur = residual(cur, c.lambda, c.vectors)
  }
  return comps
}

// ---------- k-means（確定性初始化：farthest-first） ----------
export function kmeans(points, k, iters = 100) {
  const n = points.length, d = points[0].length
  k = Math.min(k, n)
  const dist2 = (a, b) => { let s = 0; for (let i = 0; i < d; i++) s += (a[i] - b[i]) ** 2; return s }
  // 第一個中心取離整體平均最遠的點，之後每次取離已選中心最遠的點
  const mean = new Array(d).fill(0)
  for (const p of points) for (let i = 0; i < d; i++) mean[i] += p[i] / n
  const centers = []
  let first = 0, best = -1
  points.forEach((p, i) => { const s = dist2(p, mean); if (s > best) { best = s; first = i } })
  centers.push([...points[first]])
  while (centers.length < k) {
    let pick = 0; best = -1
    points.forEach((p, i) => { const s = Math.min(...centers.map(c => dist2(p, c))); if (s > best) { best = s; pick = i } })
    centers.push([...points[pick]])
  }
  let assign = new Array(n).fill(-1)
  for (let it = 0; it < iters; it++) {
    let moved = false
    points.forEach((p, i) => {
      let bi = 0, bd = Infinity
      centers.forEach((c, j) => { const s = dist2(p, c); if (s < bd) { bd = s; bi = j } })
      if (assign[i] !== bi) { assign[i] = bi; moved = true }
    })
    if (!moved) break
    centers.forEach((c, j) => {
      const members = points.filter((_, i) => assign[i] === j)
      if (!members.length) return
      for (let i = 0; i < d; i++) c[i] = members.reduce((s, p) => s + p[i], 0) / members.length
    })
  }
  return assign
}

// ---------- 沿一個 mode 分割（論文式 2 的近似解） ----------
// 1. 連續 rank-one 分解取前 R 組；2. 該 mode 上每個元素的特徵 = (λ1·v1[j], …, λR·vR[j])；
// 3. k-means 分成 k 群；4. 每群各自做非負 rank-one。
// 回傳 { groups: [[index, ...], ...]（依群內平均第一特徵由大到小排序）, parts: [{ indices, fit }], cost }
export function partitionMode(T, mode, k, R = 3) {
  const n = T.shape[mode]
  if (n < 2) return null
  const comps = successiveRankOne(T, R)
  const feats = Array.from({ length: n }, (_, j) => comps.map(c => c.lambda * c.vectors[mode][j]))
  const assign = kmeans(feats, Math.min(k, n))
  const groups = []
  for (let g = 0; g < k; g++) {
    const idx = []
    assign.forEach((a, j) => { if (a === g) idx.push(j) })
    if (idx.length) groups.push(idx)
  }
  groups.sort((a, b) => avg(b.map(j => feats[j][0])) - avg(a.map(j => feats[j][0])))
  const parts = groups.map(indices => ({ indices, fit: rankOne(subTensor(T, mode, indices)) }))
  return { mode, groups, parts, cost: parts.reduce((s, p) => s + p.fit.cost, 0) }
}
const avg = xs => xs.reduce((a, b) => a + b, 0) / xs.length

// 自動推薦：每個 mode 都試切，回傳依 cost 由小到大排序的結果
export function recommendPartition(T, k, R = 3) {
  return T.shape.map((_, m) => partitionMode(T, m, k, R)).filter(Boolean).sort((a, b) => a.cost - b.cost)
}

// ---------- 階層式分群（average linkage，歐氏距離），供 cluster heatmap 使用 ----------
// 回傳 { order: 葉節點由左到右的順序, merges: [{ a, b, height, size }], cut(k) → 每個點的群編號 }
export function hclust(points) {
  const n = points.length
  const d = (a, b) => { let s = 0; for (let i = 0; i < a.length; i++) s += (a[i] - b[i]) ** 2; return Math.sqrt(s) }
  const clusters = new Map(points.map((_, i) => [i, { id: i, members: [i] }]))
  const D = new Map()
  const key = (a, b) => (a < b ? a + ',' + b : b + ',' + a)
  for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) D.set(key(i, j), d(points[i], points[j]))
  const merges = []
  let next = n
  while (clusters.size > 1) {
    let ba = -1, bb = -1, bd = Infinity
    const ids = [...clusters.keys()]
    for (let i = 0; i < ids.length; i++) for (let j = i + 1; j < ids.length; j++) {
      const v = D.get(key(ids[i], ids[j]))
      if (v < bd) { bd = v; ba = ids[i]; bb = ids[j] }
    }
    const A = clusters.get(ba), B = clusters.get(bb)
    const C = { id: next, members: [...A.members, ...B.members], left: A, right: B, height: bd }
    for (const id of ids) {
      if (id === ba || id === bb) continue
      const v = (D.get(key(id, ba)) * A.members.length + D.get(key(id, bb)) * B.members.length) / C.members.length
      D.set(key(id, next), v)
    }
    clusters.delete(ba); clusters.delete(bb); clusters.set(next, C)
    merges.push({ a: ba, b: bb, id: next, height: bd, size: C.members.length })
    next++
  }
  const root = [...clusters.values()][0]
  const order = root.members
  const cut = k => {
    let parts = [root]
    while (parts.length < Math.min(k, n)) {
      let hi = -1, at = -1
      parts.forEach((p, i) => { if (p.left && p.height > hi) { hi = p.height; at = i } })
      if (at < 0) break
      const p = parts[at]
      parts.splice(at, 1, p.left, p.right)
    }
    const label = new Array(n)
    parts.forEach((p, g) => p.members.forEach(i => { label[i] = g }))
    return label
  }
  return { order, merges, root, cut }
}
