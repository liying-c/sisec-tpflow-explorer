// 統計與圖論工具：全部純 JavaScript，無第三方套件。
// 數學說明見 README.md 第 4.3 節。

export const isNum = v => typeof v === 'number' && Number.isFinite(v)

export function median(values) {
  const v = values.filter(isNum).sort((a, b) => a - b)
  if (!v.length) return NaN
  const m = v.length >> 1
  return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2
}

// Pearson 相關係數，忽略任一方為 NaN 的配對
export function pearson(xs, ys) {
  let n = 0, mx = 0, my = 0
  for (let i = 0; i < xs.length; i++) if (isNum(xs[i]) && isNum(ys[i])) { n++; mx += xs[i]; my += ys[i] }
  if (n < 3) return NaN
  mx /= n; my /= n
  let sxy = 0, sxx = 0, syy = 0
  for (let i = 0; i < xs.length; i++) {
    if (!isNum(xs[i]) || !isNum(ys[i])) continue
    const dx = xs[i] - mx, dy = ys[i] - my
    sxy += dx * dy; sxx += dx * dx; syy += dy * dy
  }
  return sxx > 0 && syy > 0 ? sxy / Math.sqrt(sxx * syy) : NaN
}

// A 在幾個配對樣本上贏過 B 的比例（相同不算贏）
export function winRate(a, b) {
  let win = 0, n = 0
  for (let i = 0; i < a.length; i++) {
    if (!isNum(a[i]) || !isNum(b[i])) continue
    n++
    if (a[i] > b[i]) win++
  }
  return n ? win / n : NaN
}

// ---------- Wilcoxon signed-rank test（配對樣本，常態近似） ----------
// 回傳 { z, p }，p 為雙尾。n ≥ 20 時常態近似已足夠；這裡 n = 50 首歌。
export function wilcoxon(a, b) {
  const d = []
  for (let i = 0; i < a.length; i++) {
    if (!isNum(a[i]) || !isNum(b[i])) continue
    const diff = a[i] - b[i]
    if (diff !== 0) d.push(diff)
  }
  const n = d.length
  if (n < 6) return { z: 0, p: 1, n }
  // 依 |d| 排序給名次，相同值取平均名次
  const order = d.map((v, i) => ({ v: Math.abs(v), sign: Math.sign(v), i })).sort((x, y) => x.v - y.v)
  const ranks = new Array(n)
  let tieCorrection = 0
  for (let i = 0; i < n;) {
    let j = i
    while (j + 1 < n && order[j + 1].v === order[i].v) j++
    const r = (i + j + 2) / 2          // 名次從 1 開始
    for (let k = i; k <= j; k++) ranks[order[k].i] = r
    const t = j - i + 1
    if (t > 1) tieCorrection += t * t * t - t
    i = j + 1
  }
  let wPlus = 0
  for (let i = 0; i < n; i++) if (d[i] > 0) wPlus += ranks[i]
  const mean = n * (n + 1) / 4
  const variance = n * (n + 1) * (2 * n + 1) / 24 - tieCorrection / 48
  const z = (wPlus - mean) / Math.sqrt(variance)
  const p = 2 * (1 - normalCdf(Math.abs(z)))
  return { z, p, n }
}

export function normalCdf(x) {
  // Abramowitz & Stegun 7.1.26 的 erf 近似，誤差 < 1.5e-7
  const t = 1 / (1 + 0.3275911 * Math.abs(x) / Math.SQRT2)
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x / 2)
  return x >= 0 ? 0.5 + y / 2 : 0.5 - y / 2
}

// ---------- 古典 MDS（Torgerson） ----------
// dist: n×n 距離矩陣 → 回傳 n 個二維座標。
// B = -1/2 · J D² J（雙中心化），取 B 最大的兩個特徵對，座標 = v·sqrt(λ)。
export function classicalMds(dist) {
  const n = dist.length
  const B = Array.from({ length: n }, () => new Float64Array(n))
  const rowMean = new Float64Array(n)
  let grand = 0
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
    const d2 = dist[i][j] * dist[i][j]
    B[i][j] = d2; rowMean[i] += d2 / n; grand += d2 / (n * n)
  }
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
    B[i][j] = -0.5 * (B[i][j] - rowMean[i] - rowMean[j] + grand)
  }
  const coords = Array.from({ length: n }, () => [0, 0])
  for (let dim = 0; dim < 2; dim++) {
    const { value, vector } = powerIteration(B)
    if (value <= 0) break
    const s = Math.sqrt(value)
    for (let i = 0; i < n; i++) coords[i][dim] = vector[i] * s
    // deflation：B ← B − λ v vᵀ
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) B[i][j] -= value * vector[i] * vector[j]
  }
  return coords
}

function powerIteration(A, iters = 500) {
  const n = A.length
  let v = Float64Array.from({ length: n }, (_, i) => 1 + 0.01 * i)
  let value = 0
  for (let it = 0; it < iters; it++) {
    const w = new Float64Array(n)
    for (let i = 0; i < n; i++) { let s = 0; for (let j = 0; j < n; j++) s += A[i][j] * v[j]; w[i] = s }
    let norm = 0
    for (let i = 0; i < n; i++) norm += w[i] * w[i]
    norm = Math.sqrt(norm)
    if (norm === 0) return { value: 0, vector: v }
    for (let i = 0; i < n; i++) w[i] /= norm
    let diff = 0
    for (let i = 0; i < n; i++) diff += Math.abs(w[i] - v[i])
    v = w
    value = norm
    if (diff < 1e-10) break
  }
  // Rayleigh quotient 得到特徵值（含正負號）
  let num = 0
  for (let i = 0; i < n; i++) { let s = 0; for (let j = 0; j < n; j++) s += A[i][j] * v[j]; num += v[i] * s }
  return { value: num, vector: v }
}

// ---------- 有向圖：遞移化簡與分層 ----------
// edges: [[from, to], ...] 表示 from 優於 to。假設無環（優劣關係由中位數排序保證）。
export function transitiveReduction(nodes, edges) {
  const out = new Map(nodes.map(n => [n, new Set()]))
  for (const [a, b] of edges) out.get(a)?.add(b)
  // reach[a] = 從 a 經過 ≥2 步可到的節點
  const memo = new Map()
  const reach = a => {
    if (memo.has(a)) return memo.get(a)
    const r = new Set()
    for (const b of out.get(a)) { r.add(b); for (const c of reach(b)) r.add(c) }
    memo.set(a, r)
    return r
  }
  const kept = []
  for (const [a, b] of edges) {
    let redundant = false
    for (const c of out.get(a)) if (c !== b && reach(c).has(b)) { redundant = true; break }
    if (!redundant) kept.push([a, b])
  }
  return kept
}

// 最長路徑分層：layer[n] = 0 表示沒有人顯著優於它（頂層）
export function layerByLongestPath(nodes, edges) {
  const incoming = new Map(nodes.map(n => [n, []]))
  for (const [a, b] of edges) incoming.get(b)?.push(a)
  const memo = new Map()
  const layer = n => {
    if (memo.has(n)) return memo.get(n)
    memo.set(n, 0)   // 防環
    const l = incoming.get(n).length ? 1 + Math.max(...incoming.get(n).map(layer)) : 0
    memo.set(n, l)
    return l
  }
  return new Map(nodes.map(n => [n, layer(n)]))
}
