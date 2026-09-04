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

    def test_python_rust_import_is_explicit_opt_in(self):
        bridge = (ROOT / "writing_agent/v2/rust_bridge.py").read_text(encoding="utf-8")
        tree = ast.parse(bridge)
        checks = [node for node in ast.walk(tree) if isinstance(node, ast.Compare) and "WA_USE_RUST_ENGINE" in ast.unparse(node)]
        self.assertGreaterEqual(len(checks), 2)
        self.assertNotIn("subprocess.run([\"cargo\"", bridge)

    def test_node_gateway_remains_explicit_opt_in(self):
        factory = (ROOT / "writing_agent/llm/factory.py").read_text(encoding="utf-8")
        self.assertIn('WRITING_AGENT_LLM_BACKEND", "python"', factory)
        self.assertIn('backend != "node"', factory)


if __name__ == "__main__":
    unittest.main()
