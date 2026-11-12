// 全站共用的 tooltip 狀態：各圖表呼叫 showTip / hideTip，App.vue 負責渲染那個 div。
import { reactive } from 'vue'

export const tip = reactive({ show: false, x: 0, y: 0, html: '' })

export function showTip(event, html) {
  tip.show = true
  tip.html = html
  moveTip(event)
}

export function moveTip(event) {
  const pad = 14
  const w = 260
  const x = event.clientX + pad + w > window.innerWidth ? event.clientX - pad - w : event.clientX + pad
  tip.x = x
  tip.y = event.clientY + pad
}

export function hideTip() {
  tip.show = false
}
