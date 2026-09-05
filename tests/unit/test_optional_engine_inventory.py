import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class OptionalEngineInventoryTests(unittest.TestCase):
    def test_frontend_does_not_probe_missing_wasm_on_startup(self):
        frontend = ROOT / "writing_agent/web/frontend_svelte/src"
        sources = "\n".join(path.read_text(encoding="utf-8") for path in frontend.rglob("*") if path.suffix in {".ts", ".svelte"})
        self.assertNotIn("initWasmEngine", sources)
        self.assertNotIn("isWasmAvailable", sources)
        self.assertNotIn("data-engine", sources)
        self.assertNotIn("rustEngineReady", sources)
        self.assertFalse((frontend / "lib/engine/wasmLoader.ts").exists())

    def test_retired_optional_engines_are_absent(self):
        factory = (ROOT / "writing_agent/llm/factory.py").read_text(encoding="utf-8")
        self.assertFalse((ROOT / "writing_agent/v2/rust_bridge.py").exists())
        self.assertFalse((ROOT / "writing_agent/llm/providers/node_ai_gateway_provider.py").exists())
        self.assertNotIn("node_gateway", factory)
        self.assertNotIn("WRITING_AGENT_LLM_BACKEND", factory)


if __name__ == "__main__":
    unittest.main()
