from scripts import golden_export_regression


def test_golden_export_regression_script() -> None:
    code = golden_export_regression.main(['--out', '.data/out/test_golden_export_regression.json'])
    assert code == 0
