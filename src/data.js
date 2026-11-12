// 資料載入與索引。CSV 由 prepare_data.py 產生在 public/data/。
import * as d3 from 'd3'

export async function loadAll(base) {
  const [systems, tracks, scores] = await Promise.all([
    d3.csv(`${base}data/systems.csv`),
    d3.csv(`${base}data/tracks.csv`, d3.autoType),
    d3.csv(`${base}data/scores_track.csv`, d3.autoType),
  ])
  // index.get(system).get(target).get(track_id) → { SDR, SIR, SAR, ISR }
  const index = new Map()
  for (const r of scores) {
    if (!index.has(r.system)) index.set(r.system, new Map())
    const byTarget = index.get(r.system)
    if (!byTarget.has(r.target)) byTarget.set(r.target, new Map())
    byTarget.get(r.target).set(r.track_id, r)
  }
  const systemInfo = new Map(systems.map(s => [s.system, s]))
  const trackInfo = new Map(tracks.map(t => [t.track_id, t]))
  return { systems, tracks, scores, index, systemInfo, trackInfo }
}

// 某系統在某 target / metric 上、依 trackIds 順序的分數陣列（缺值為 NaN）
export function profile(index, system, target, metric, trackIds) {
  const m = index.get(system)?.get(target)
  return trackIds.map(t => {
    const v = m?.get(t)?.[metric]
    return typeof v === 'number' && Number.isFinite(v) ? v : NaN
  })
}

export function loadFrames(base, trackId) {
  return d3.csv(`${base}data/frames/${trackId}.csv`, d3.autoType)
}

// 作者字串 → 正規化後的姓名集合（去掉「(implementation author)」這類註記）
export function authorSet(authorsField) {
  return new Set(
    (authorsField || '')
      .split(/,| and /i)
      .map(s => s.replace(/\(.*?\)/g, '').trim().toLowerCase())
      .filter(s => s.length > 3),
  )
}
