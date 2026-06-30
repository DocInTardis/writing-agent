let wasmInitDone = false

export async function initWasmEngine(): Promise<boolean> {
  if (wasmInitDone) return true
  try {
    const wasm = await import('../../../public/wasm/wa_bridge.js')
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
