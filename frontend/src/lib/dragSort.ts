import { ref } from 'vue'

interface DragState {
  scope: string
  from: number
  over: number | null
}

/**
 * 原生 HTML5 拖拽排序。只有按住把手（drag.handle）时行才可拖动，避免干扰行内输入框；
 * scope 区分不同列表（例如每个分组各自的成员列表），跨列表拖放会被忽略。
 */
export function useDragSort() {
  const armed = ref<{ scope: string; index: number } | null>(null)
  const state = ref<DragState | null>(null)

  function reset() {
    armed.value = null
    state.value = null
  }

  function handle(scope: string, index: number) {
    return {
      class: 'drag-handle',
      title: '拖动排序',
      'aria-hidden': true,
      onMousedown: () => { armed.value = { scope, index } },
      onMouseup: () => { armed.value = null },
    }
  }

  function row(scope: string, index: number, onMove: (from: number, to: number) => void) {
    const s = state.value
    const active = s?.scope === scope
    return {
      draggable: armed.value?.scope === scope && armed.value.index === index,
      class: {
        'is-dragging': active && s.from === index,
        'drop-before': active && s.over === index && index < s.from,
        'drop-after': active && s.over === index && index > s.from,
      },
      onDragstart: (e: DragEvent) => {
        if (armed.value?.scope !== scope || armed.value.index !== index) return
        e.stopPropagation()
        state.value = { scope, from: index, over: null }
        if (e.dataTransfer) {
          e.dataTransfer.effectAllowed = 'move'
          e.dataTransfer.setData('text/plain', '') // Firefox 需要 setData 才会开始拖动
        }
      },
      onDragover: (e: DragEvent) => {
        if (state.value?.scope !== scope) return
        e.preventDefault()
        e.stopPropagation()
        if (e.dataTransfer) e.dataTransfer.dropEffect = 'move'
        state.value.over = index
      },
      onDrop: (e: DragEvent) => {
        if (state.value?.scope !== scope) return
        e.preventDefault()
        e.stopPropagation()
        const from = state.value.from
        reset()
        if (from !== index) onMove(from, index)
      },
      onDragend: reset,
    }
  }

  return { handle, row }
}
