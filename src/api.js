// 計算後端（backend/sisec，FastAPI）的用戶端。演算法全部在後端，這裡只負責收送資料。
// 逐秒分數（時間線用）是純顯示資料，仍直接讀靜態 CSV。
import * as d3 from 'd3'

// 建置時由 VITE_API_URL 指定後端網址；沒指定時走同源的 /api（開發時由 Vite proxy 轉到本機 uvicorn）
const API = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')

// JSON 沒有 NaN，後端用 null 表示缺值；在這一處轉回 NaN，其餘程式照舊用 Number.isFinite 判斷
function withNaN(value) {
  if (value === null) return NaN
  if (Array.isArray(value)) return value.map(withNaN)
  if (typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, withNaN(v)]))
  return value
}

async function request(path, body) {
  let res
  try {
    res = await fetch(`${API}/api/${path}`, body === undefined ? undefined : {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body),
    })
  } catch {
    throw new Error('沒有回應')
  }
  if (!res.ok) {
    const detail = await res.json().then(j => (typeof j.detail === 'string' ? j.detail : ''), () => '')
    throw new Error(`HTTP ${res.status}${detail ? '：' + detail : ''}`)
  }
  return withNaN(await res.json())
}

export const api = {
  meta: () => request('meta'),
  overview: q => request('overview', q),            // { metric, target, categories }
  stage: q => request('stage', q),                  // { categories }
  cluster: q => request('cluster', q),              // { categories, metric }
  summary: q => request('partition/summary', q),    // { categories, idx }
  split: q => request('partition/split', q),        // { categories, idx, mode, k }
}

export function loadFrames(trackId) {
  return d3.csv(`${import.meta.env.BASE_URL}data/frames/${trackId}.csv`, d3.autoType)
}
