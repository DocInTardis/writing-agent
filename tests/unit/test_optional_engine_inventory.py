import ast
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

    def test_rust_engine_is_available_without_runtime_build(self):
        bridge_path = ROOT / "writing_agent/v2/rust_bridge.py"
        self.assertTrue((ROOT / "engine/core/Cargo.toml").exists())
        self.assertTrue((ROOT / "engine/engine/Cargo.toml").exists())
        self.assertTrue((ROOT / "engine/bridge/Cargo.toml").exists())
        bridge = bridge_path.read_text(encoding="utf-8")
        tree = ast.parse(bridge)
        checks = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Compare) and "WA_USE_RUST_ENGINE" in ast.unparse(node)
        ]
        self.assertGreaterEqual(len(checks), 2)
        self.assertNotIn('subprocess.run(["cargo"', bridge)

    def test_node_gateway_remains_retired(self):
        factory = (ROOT / "writing_agent/llm/factory.py").read_text(encoding="utf-8")
        self.assertFalse((ROOT / "writing_agent/llm/providers/node_ai_gateway_provider.py").exists())
        self.assertNotIn("node_gateway", factory)
        self.assertNotIn("WRITING_AGENT_LLM_BACKEND", factory)


if __name__ == "__main__":
    unittest.main()
