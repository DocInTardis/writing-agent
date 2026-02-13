// WASM 编辑器初始化
let wasmModule: any = null
let WasmEditor: any = null

export async function initWasmEngine(): Promise<boolean> {
  try {
    if (WasmEditor) return true
    wasmModule = await import('./wasm/wa_bridge.js')
    if (wasmModule?.default) {
      await wasmModule.default()
    }
    WasmEditor = wasmModule?.WasmEditor ?? null
    if (!WasmEditor) {
      console.warn('未找到 Rust WASM 入口：WasmEditor')
      return false
    }
    console.log('已加载 Rust WASM 引擎')
    return true
  } catch (error) {
    console.warn('Rust WASM 加载失败，回退到 contenteditable：', error)
    return false
  }
}

export function createWasmEditor() {
  if (!WasmEditor) {
    throw new Error('WASM 未初始化，请先调用 initWasmEngine()')
  }
  return new WasmEditor()
}

export function isWasmAvailable(): boolean {
  return WasmEditor !== null
}
