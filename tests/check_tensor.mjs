// 驗證 src/tensor.js：npm run check
import { makeNode, splitNode, unsplit, flatten, modeSummary, representative } from '../src/partition.js'
import { makeTensor, subTensor, percentileRanks, rankOne, successiveRankOne, kmeans, partitionMode, recommendPartition, hclust } from '../src/tensor.js'

let failed = 0
const check = (name, ok, detail = '') => { console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  (' + detail + ')' : ''}`); if (!ok) failed++ }

// 用外積建立 rank-one 張量
function outer(vectors, scale = 1) {
  const T = makeTensor(vectors.map(v => v.length))
  const idx = new Array(vectors.length).fill(0)
  for (let f = 0; f < T.data.length; f++) {
    let p = scale
    for (let m = 0; m < vectors.length; m++) p *= vectors[m][idx[m]]
    T.data[f] = p
    for (let m = vectors.length - 1; m >= 0; m--) { if (++idx[m] < vectors[m].length) break; idx[m] = 0 }
  }
  return T
}
const sameSets = (groups, expected) => {
  const norm = gs => gs.map(g => [...g].sort((a, b) => a - b).join(',')).sort().join('|')
  return norm(groups) === norm(expected)
}

{
  const p = percentileRanks([10, 30, 20, 20])
  check('percentileRanks 名次與同值平均', p[0] === 0.125 && p[1] === 0.875 && p[2] === 0.5 && p[3] === 0.5, p.join(', '))
}

{
  const T = outer([[1, 2, 3], [0.5, 1, 1.5, 2], [2, 1]])
  const r = rankOne(T)
  check('rankOne：rank-one 張量的 cost ≈ 0', r.cost < 1e-12, `cost = ${r.cost.toExponential(2)}`)
  const ratio = r.vectors[0][2] / r.vectors[0][0]
  check('rankOne：還原各維度的比例', Math.abs(ratio - 3) < 1e-6, `v0[2]/v0[0] = ${ratio.toFixed(6)}`)
  check('rankOne：向量為單位長度且非負', r.vectors.every(v => Math.abs(Math.hypot(...v) - 1) < 1e-9 && v.every(x => x >= 0)))
}

{
  const T = outer([[1, 2], [3, 1, 2]])
  const S = subTensor(T, 1, [2, 0])
  check('subTensor 取出指定切片', S.shape.join('x') === '2x2' && S.data[0] === 2 && S.data[1] === 3 && S.data[2] === 4 && S.data[3] === 6, [...S.data].join(', '))
}

{
  const a = kmeans([[0, 0], [0.1, 0], [5, 5], [5.1, 5], [0, 0.1]], 2)
  check('kmeans 分出兩群', a[0] === a[1] && a[1] === a[4] && a[2] === a[3] && a[0] !== a[2], a.join(''))
}

// 植入兩群：mode 1 的前 4 個與後 4 個元素，在 mode 0 上有不同的分佈
{
  const A = outer([[1, 2, 3, 4, 5], [1, 1.2, 0.9, 1.1], [1, 2, 1]])
  const B = outer([[5, 4, 3, 2, 1], [1, 0.8, 1.1, 1.2], [1, 2, 1]])
  const T = makeTensor([5, 8, 3])
  for (let i = 0; i < 5; i++) for (let j = 0; j < 8; j++) for (let k = 0; k < 3; k++) {
    const src = j < 4 ? A : B
    T.data[(i * 8 + j) * 3 + k] = src.data[(i * 4 + (j % 4)) * 3 + k]
  }
  const whole = rankOne(T)
  const part = partitionMode(T, 1, 2)
  check('partitionMode 找回植入的兩群', sameSets(part.groups, [[0, 1, 2, 3], [4, 5, 6, 7]]), JSON.stringify(part.groups))
  check('分割後 cost ≈ 0（每群都是 rank-one）', part.cost < 1e-10, `cost = ${part.cost.toExponential(2)}`)
  check('分割後 cost ≤ 分割前', part.cost <= whole.cost + 1e-12, `${part.cost.toExponential(2)} ≤ ${whole.cost.toExponential(2)}`)
  const rec = recommendPartition(T, 2)
  check('recommendPartition 推薦植入的 mode', rec[0].mode === 1, `modes by cost: ${rec.map(r => r.mode).join(', ')}`)
  const comps = successiveRankOne(T, 3)
  check('successiveRankOne：強度遞減', comps.length >= 2 && comps[0].lambda >= comps[1].lambda, comps.map(c => c.lambda.toFixed(3)).join(' ≥ '))
}

{
  const h = hclust([[0], [10], [0.2], [10.3], [0.1]])
  const lab = h.cut(2)
  check('hclust.cut(2) 分出兩群', lab[0] === lab[2] && lab[2] === lab[4] && lab[1] === lab[3] && lab[0] !== lab[1], lab.join(''))
  check('hclust.order 同群相鄰', (() => { const pos = h.order.map(i => lab[i]); return pos.join('').replace(/(.)\1*/g, '$1').length === 2 })(), h.order.join(','))
}

// ---------- partition.js：分割樹 ----------
{
  const range = n => Array.from({ length: n }, (_, i) => i)
  // 與前面相同的植入資料：mode 1 的前 4 個與後 4 個元素有不同的 mode 0 分佈
  const A = outer([[1, 2, 3, 4, 5], [1, 1.2, 0.9, 1.1], [1, 2, 1]])
  const B = outer([[5, 4, 3, 2, 1], [1, 0.8, 1.1, 1.2], [1, 2, 1]])
  const T = makeTensor([5, 8, 3])
  for (let i = 0; i < 5; i++) for (let j = 0; j < 8; j++) for (let k = 0; k < 3; k++) T.data[(i * 8 + j) * 3 + k] = (j < 4 ? A : B).data[(i * 4 + (j % 4)) * 3 + k]
  const root = makeNode(T, T.shape.map(range))
  check('makeNode：根節點涵蓋全部且未解釋比例 > 0', root.idx[1].length === 8 && root.unexplained > 0.01, root.unexplained.toFixed(3))
  check('splitNode 沿 mode 1 切 2 群', splitNode(T, root, 1, 2) && root.children.length === 2 && root.splitMode === 1)
  check('子節點的索引是基底索引且互不重疊', sameSets(root.children.map(c => c.idx[1]), [[0, 1, 2, 3], [4, 5, 6, 7]]) && root.children.every(c => c.idx[0].length === 5))
  check('子節點的未解釋比例 ≈ 0', root.children.every(c => c.unexplained < 1e-10))
  check('rec 列出三個維度的降幅，mode 1 降幅 ≈ 100%', root.rec.length === 3 && Math.abs(root.rec.find(r => r.mode === 1).reduction - 1) < 1e-9)
  const s = modeSummary(root.children[0], 0)
  check('modeSummary：rank-one 區塊的四分位偏差 ≈ 0', s.length === 5 && s.every(x => Math.abs(x.q1) < 1e-9 && Math.abs(x.med) < 1e-9 && Math.abs(x.q3) < 1e-9))
  check('modeSummary：摘要值隨植入的分佈遞增或遞減', s.every((x, i) => i === 0 || (x.model - s[i - 1].model) * (s[1].model - s[0].model) > 0), s.map(x => x.model.toFixed(1)).join(' '))
  check('representative 取摘要值居中的元素', representative(root.children[0], 0) === 2, String(representative(root.children[0], 0)))
  // 第二層分割：對第一個子節點沿 mode 0 再切
  const child = root.children[0]
  check('第二層 splitNode', splitNode(T, child, 0, 2) && child.children.length === 2 && child.children.every(c => c.parent === child && c.idx[1].length === 4))
  check('flatten 走訪全部節點並帶深度', flatten(root).length === 5 && Math.max(...flatten(root).map(f => f.depth)) === 2)
  unsplit(root)
  check('unsplit 後回到單一節點', root.children.length === 0 && root.splitMode === null && flatten(root).length === 1)
  check('unsplit 後可再次分割', splitNode(T, root, 'auto', 2) && root.splitMode === 1)
}

console.log(failed ? `\n${failed} check(s) failed` : '\nall checks passed')
process.exit(failed ? 1 : 0)
