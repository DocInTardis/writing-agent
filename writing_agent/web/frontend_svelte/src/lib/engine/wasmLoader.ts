let wasmInitDone = false

export async function initWasmEngine(): Promise<boolean> {
  if (wasmInitDone) return true
  try {
    const wasmUrl = '/wasm/wa_bridge.js'
    const wasm = await import(/* @vite-ignore */ wasmUrl)
    if (wasm && typeof wasm.init === 'function') {
      await wasm.init()
    }
    wasmInitDone = true
    return true
  } catch {
    wasmInitDone = false
    return false
  }
}

export function isWasmAvailable(): boolean {
  return wasmInitDone
}
