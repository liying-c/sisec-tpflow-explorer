// 包住一個非同步函式：連續呼叫時只有最後一次的結果有效，較早的一律得到 undefined。
// 快速連點控制項時，較慢回來的舊回應才不會蓋掉新的畫面。
export function latest(fn) {
  let seq = 0
  return async (...args) => {
    const mine = ++seq
    try {
      const result = await fn(...args)
      return mine === seq ? result : undefined
    } catch (e) {
      if (mine === seq) throw e
      return undefined
    }
  }
}
