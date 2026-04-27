from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the ``--run-slow`` flag used to gate kernel-driven determinism tests."""
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="Run slow tests that spin up real Jupyter kernels.",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register the ``slow`` marker so tests can opt into kernel execution."""
    config.addinivalue_line("markers", "slow: requires --run-slow to execute")


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip slow tests unless the user passes ``--run-slow``."""
    if config.getoption("--run-slow"):
        return
    skip_slow = pytest.mark.skip(reason="needs --run-slow")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
