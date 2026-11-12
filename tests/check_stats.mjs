// 驗證 src/stats.js：npm run check
import { median, pearson, winRate, wilcoxon, normalCdf, classicalMds, transitiveReduction, layerByLongestPath } from '../src/stats.js'

let failed = 0
const check = (name, ok, detail = '') => { console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  (' + detail + ')' : ''}`); if (!ok) failed++ }

check('median 奇數個', median([3, 1, 2]) === 2)
check('median 偶數個、忽略 NaN', median([4, NaN, 1, 2, 3, null]) === 2.5)
check('pearson 完全線性 = 1', Math.abs(pearson([1, 2, 3, 4], [2, 4, 6, 8]) - 1) < 1e-12)
check('pearson 反向 = -1', Math.abs(pearson([1, 2, 3], [3, 2, 1]) + 1) < 1e-12)
check('winRate', winRate([3, 2, 1, 5], [1, 2, 2, 4]) === 0.5)
check('normalCdf(1.96) ≈ 0.975', Math.abs(normalCdf(1.96) - 0.975) < 1e-3, normalCdf(1.96).toFixed(4))

// Wilcoxon：A 幾乎每次都贏 → p 很小；A、B 對稱 → p 大
{
  const a = Array.from({ length: 50 }, (_, i) => 10 + Math.sin(i))
  const b = a.map((v, i) => v - 1 + 0.3 * Math.cos(3 * i))
  const r1 = wilcoxon(a, b)
  const sym = a.map((v, i) => v + (i % 2 ? 0.5 : -0.5))
  const r2 = wilcoxon(a, sym)
  check('wilcoxon 明顯優於 → p < 0.001', r1.p < 1e-3, `p = ${r1.p.toExponential(2)}`)
  check('wilcoxon 對稱差異 → p > 0.5', r2.p > 0.5, `p = ${r2.p.toFixed(3)}`)
}

// MDS：把平面上的四個點用距離矩陣還原，兩兩距離應一致
{
  const pts = [[0, 0], [3, 0], [0, 4], [3, 4]]
  const d = pts.map(p => pts.map(q => Math.hypot(p[0] - q[0], p[1] - q[1])))
  const xy = classicalMds(d)
  let maxErr = 0
  for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) {
    maxErr = Math.max(maxErr, Math.abs(Math.hypot(xy[i][0] - xy[j][0], xy[i][1] - xy[j][1]) - d[i][j]))
  }
  check('classicalMds 還原平面距離', maxErr < 1e-6, `max |err| = ${maxErr.toExponential(2)}`)
}

// 遞移化簡與分層：A>B, B>C, A>C → 去掉 A>C；層數 A=0, B=1, C=2
{
  const nodes = ['A', 'B', 'C', 'D']
  const edges = [['A', 'B'], ['B', 'C'], ['A', 'C'], ['A', 'D']]
  const red = transitiveReduction(nodes, edges)
  check('transitiveReduction 去掉可推得的邊', red.length === 3 && !red.some(e => e[0] === 'A' && e[1] === 'C'), JSON.stringify(red))
  const layers = layerByLongestPath(nodes, red)
  check('layerByLongestPath', layers.get('A') === 0 && layers.get('B') === 1 && layers.get('C') === 2 && layers.get('D') === 1)
}

console.log(failed ? `\n${failed} check(s) failed` : '\nall checks passed')
process.exit(failed ? 1 : 0)
