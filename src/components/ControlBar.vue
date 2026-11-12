<script setup>
// 全域控制列：指標、stem、系統類別開關、清除選取。所有視圖同步。
import { CATEGORIES, METRICS, TARGETS } from '../series.js'

const metric = defineModel('metric', { type: String, required: true })
const target = defineModel('target', { type: String, required: true })
const cats = defineModel('cats', { type: Object, required: true })   // Set

defineProps({
  selectedCount: { type: Number, default: 0 },
  selectedTrack: { type: String, default: '' },
})
const emit = defineEmits(['clear'])

function toggleCat(key) {
  const next = new Set(cats.value)
  if (next.has(key)) { if (next.size > 1) next.delete(key) } else next.add(key)
  cats.value = next
}
</script>

<template>
  <div class="controls">
    <div class="control-group">
      <span class="control-label">指標</span>
      <div class="seg" role="radiogroup" aria-label="指標">
        <button v-for="m in METRICS" :key="m.key" type="button" role="radio"
          :aria-checked="metric === m.key" :class="{ on: metric === m.key }" :title="m.desc"
          @click="metric = m.key">{{ m.name }}</button>
      </div>
    </div>
    <div class="control-group">
      <span class="control-label">Stem</span>
      <div class="seg" role="radiogroup" aria-label="stem">
        <button v-for="t in TARGETS" :key="t.key" type="button" role="radio"
          :aria-checked="target === t.key" :class="{ on: target === t.key }"
          @click="target = t.key">{{ t.name }}</button>
      </div>
    </div>
    <div class="control-group">
      <span class="control-label">系統類別</span>
      <div class="cats">
        <button v-for="c in CATEGORIES" :key="c.key" type="button" class="cat-toggle"
          :class="{ off: !cats.has(c.key) }" :aria-pressed="cats.has(c.key)" @click="toggleCat(c.key)">
          <span class="swatch" :style="{ background: c.color }"></span>{{ c.name }}
        </button>
      </div>
    </div>
    <div class="control-group">
      <span class="control-label">選取</span>
      <span class="control-readout">
        {{ selectedCount ? `${selectedCount} 個系統` : '未選取系統' }}<template v-if="selectedTrack">、曲目 {{ selectedTrack }}</template>
      </span>
      <button type="button" class="secondary" :disabled="!selectedCount && !selectedTrack" @click="emit('clear')">清除</button>
    </div>
  </div>
</template>
