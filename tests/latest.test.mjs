// 快速連點控制項時，較慢回來的舊回應不能蓋掉新的畫面：latest() 只讓最後一次呼叫的結果有效。
import test from 'node:test'
import assert from 'node:assert/strict'
import { latest } from '../src/latest.js'

const after = (ms, value) => new Promise(resolve => setTimeout(() => resolve(value), ms))
const failAfter = (ms, message) => new Promise((_, reject) => setTimeout(() => reject(new Error(message)), ms))

test('較早的呼叫比較晚回來時被丟棄', async () => {
  const fetchIt = latest((ms, value) => after(ms, value))
  const [slow, fast] = await Promise.all([fetchIt(40, 'old'), fetchIt(5, 'new')])
  assert.equal(slow, undefined)
  assert.equal(fast, 'new')
})

test('只有一次呼叫時原樣回傳', async () => {
  assert.equal(await latest(v => after(1, v))('only'), 'only')
})

test('過期呼叫的錯誤不往外丟，最新呼叫的錯誤照常丟出', async () => {
  const fetchIt = latest((ms, message) => failAfter(ms, message))
  const stale = fetchIt(30, 'stale')
  const current = fetchIt(5, 'current')
  await assert.rejects(current, /current/)
  assert.equal(await stale, undefined)
})
