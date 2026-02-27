from __future__ import annotations

from scripts import capacity_stress_matrix


def test_profile_catalog_quick_contains_expected_profiles() -> None:
    profiles = capacity_stress_matrix._profile_catalog(quick=True)
    assert set(profiles.keys()) == {"peak", "burst", "jitter"}
    assert int(profiles["peak"]["requests"]) > 0


def test_parse_profiles_filters_unknown_and_falls_back() -> None:
    profiles = capacity_stress_matrix._profile_catalog(quick=True)
    selected = capacity_stress_matrix._parse_profiles("peak,unknown,jitter", profiles)
    assert selected == ["peak", "jitter"]
    fallback = capacity_stress_matrix._parse_profiles("unknown,none", profiles)
    assert fallback == ["peak", "burst", "jitter"]
