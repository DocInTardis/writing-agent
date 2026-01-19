from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class OllamaError(RuntimeError):
    pass


@dataclass(frozen=True)
class OllamaClient:
    base_url: str
    model: str
    timeout_s: float = 60.0

    def is_running(self) -> bool:
        try:
            self._request_json("GET", "/api/tags", None)
            return True
        except Exception:
            return False

    def has_model(self) -> bool:
        data = self._request_json("GET", "/api/tags", None)
        models = data.get("models") if isinstance(data, dict) else None
        if not isinstance(models, list):
            return False
        for m in models:
            name = (m.get("name") if isinstance(m, dict) else "") or ""
            if name == self.model:
                return True
        return False

    def pull_model(self) -> None:
        payload = {"name": self.model, "stream": False}
        self._request_json("POST", "/api/pull", payload)

    def chat(self, system: str, user: str, temperature: float = 0.2, options: dict[str, Any] | None = None) -> str:
        opts: dict[str, Any] = {"temperature": temperature}
        if options:
            opts.update({k: v for k, v in options.items() if v is not None})
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": opts,
        }
        data = self._request_json("POST", "/api/chat", payload)
        if not isinstance(data, dict):
            raise OllamaError("Ollama返回非JSON对象")
        msg = data.get("message")
        if not isinstance(msg, dict) or "content" not in msg:
            raise OllamaError("Ollama返回缺少message.content")
        return str(msg.get("content") or "")

    def embeddings(self, *, prompt: str, model: str | None = None) -> list[float]:
        """
        Returns a single embedding vector.
        Supports Ollama variants:
          - POST /api/embeddings {"model","prompt"}
          - POST /api/embed {"model","input"} (newer)
        """
        m = (model or self.model or "").strip()
        if not m:
            raise OllamaError("embedding model required")
        p = (prompt or "").strip()
        if not p:
            return []

        # Legacy endpoint
        try:
            data = self._request_json("POST", "/api/embeddings", {"model": m, "prompt": p})
            if isinstance(data, dict):
                emb = data.get("embedding")
                if isinstance(emb, list):
                    return [float(x) for x in emb]
        except Exception:
            pass

        # Newer endpoint
        data2 = self._request_json("POST", "/api/embed", {"model": m, "input": p})
        if isinstance(data2, dict):
            embs = data2.get("embeddings")
            if isinstance(embs, list) and embs and isinstance(embs[0], list):
                return [float(x) for x in embs[0]]
            if isinstance(embs, list) and all(isinstance(x, (int, float)) for x in embs):
                return [float(x) for x in embs]
        raise OllamaError("Ollama返回缺少embedding")

    def chat_stream(self, system: str, user: str, temperature: float = 0.2, options: dict[str, Any] | None = None):
        opts: dict[str, Any] = {"temperature": temperature}
        if options:
            opts.update({k: v for k, v in options.items() if v is not None})
        payload = {
            "model": self.model,
            "stream": True,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": opts,
        }
        url = f"{self.base_url}/api/chat"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url=url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(data, dict) and data.get("done") is True:
                        break
                    msg = data.get("message") if isinstance(data, dict) else None
                    if isinstance(msg, dict):
                        delta = str(msg.get("content") or "")
                        if delta:
                            yield delta
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else str(e)
            raise OllamaError(f"Ollama HTTP错误: {e.code} {e.reason}: {detail}") from e
        except Exception as e:
            raise OllamaError(f"无法连接Ollama: {e}") from e

    def _request_json(self, method: str, path: str, payload: dict[str, Any] | None) -> Any:
        url = f"{self.base_url}{path}"
        body = None
        headers = {"Content-Type": "application/json"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url=url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else str(e)
            raise OllamaError(f"Ollama HTTP错误: {e.code} {e.reason}: {detail}") from e
        except Exception as e:
            raise OllamaError(f"无法连接Ollama: {e}") from e

        try:
            return json.loads(raw) if raw else {}
        except Exception as e:
            raise OllamaError(f"Ollama返回无法解析JSON: {raw[:2000]}") from e
