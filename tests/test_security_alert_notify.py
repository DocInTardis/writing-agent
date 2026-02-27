from __future__ import annotations

import hashlib
import hmac

from scripts import security_alert_notify


def test_extract_failed_check_ids_parses_list_lines() -> None:
    details = """
    - npm_prod_critical: value=1 expect=<=0
    - npm_dev_high: value=2 expect=<=0
    random line
    - npm_dev_high: duplicated
    """
    out = security_alert_notify._extract_failed_check_ids(details)
    assert out == ["npm_prod_critical", "npm_dev_high"]


def test_triage_hints_cover_regression_and_pip() -> None:
    ids = ["npm_prod_total_regression", "pip_total_vulns"]
    hints = security_alert_notify._triage_hints(ids)
    assert any("baseline" in row.lower() for row in hints)
    assert any("pip-audit" in row.lower() for row in hints)


def test_signature_headers_match_expected_hmac() -> None:
    payload = b'{"hello":"world"}'
    headers = security_alert_notify._signature_headers(body=payload, signing_key="secret", ts=1700000000)
    expected_msg = b"1700000000." + payload
    expected = hmac.new(b"secret", expected_msg, hashlib.sha256).hexdigest()
    assert headers["X-WA-Timestamp"] == "1700000000"
    assert headers["X-WA-Signature"] == f"sha256={expected}"


def test_parse_ids_arg_handles_newline_and_comma() -> None:
    raw = "npm_prod_critical,\n pip_total_vulns, npm_prod_critical"
    out = security_alert_notify._parse_ids_arg(raw)
    assert out == ["npm_prod_critical", "pip_total_vulns"]
