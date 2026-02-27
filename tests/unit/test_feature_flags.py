from __future__ import annotations

import json
from pathlib import Path

from writing_agent.feature_flags import FeatureFlags


def test_feature_flags_enabled_and_rollout(tmp_path: Path) -> None:
    path = tmp_path / "flags.json"
    path.write_text(
        json.dumps(
            {
                "flags": {
                    "node_ai_gateway_backend": {
                        "enabled": True,
                        "rollout_percent": 20,
                        "tenants": ["internal"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    flags = FeatureFlags(path)
    assert flags.enabled("node_ai_gateway_backend", tenant_id="internal") is True
    assert flags.rollout_percent("node_ai_gateway_backend", tenant_id="internal") == 20
    assert flags.rollout_percent("node_ai_gateway_backend", tenant_id="external") == 0
