import pytest


@pytest.mark.skip(reason='Playwright matrix executed in dedicated workflow')
def test_e2e_placeholder() -> None:
    assert True
