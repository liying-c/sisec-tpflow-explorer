// 顏色跟著「系統類別」走，不跟著個別系統走（31 個系統不可能有 31 種可分辨的顏色）。
// 色票定義在 style.css（含深色模式），已用 dataviz 驗證器檢查色盲可分辨性。
export const CATEGORIES = [
  { key: 'supervised',       name: '監督式學習',        short: '監督式',  color: 'var(--series-1)' },
  { key: 'supervised+extra', name: '監督式 + 額外訓練資料', short: '監督式+資料', color: 'var(--series-3)' },
  { key: 'blind',            name: '盲分離（無訓練）',    short: '盲分離',  color: 'var(--series-2)' },
  { key: 'oracle',           name: 'Oracle（理論上界 / 下界）', short: 'Oracle', color: 'var(--series-oracle)' },
]
export const CATEGORY = Object.fromEntries(CATEGORIES.map(c => [c.key, c]))

export const METRICS = [
  { key: 'SDR', name: 'SDR', desc: '整體失真比：所有錯誤加總' },
  { key: 'SIR', name: 'SIR', desc: '干擾比：其他來源漏進來多少' },
  { key: 'SAR', name: 'SAR', desc: '瑕疵比：產生了多少不自然的人工痕跡' },
  { key: 'ISR', name: 'ISR', desc: '空間失真比：立體聲像保留得好不好' },
]

export const TARGETS = [
  { key: 'vocals', name: '人聲 vocals' },
  { key: 'drums', name: '鼓 drums' },
  { key: 'bass', name: '貝斯 bass' },
  { key: 'other', name: '其他 other' },
  { key: 'accompaniment', name: '伴奏 accompaniment' },
]
