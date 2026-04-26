from __future__ import annotations

import nborder


def test_package_exposes_version_string() -> None:
    assert nborder.__version__
