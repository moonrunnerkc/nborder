from __future__ import annotations

from nborder.config import DEFAULT_SEED_LIBRARIES, _string_tuple


def test_string_tuple_accepts_tuple_values() -> None:
    assert _string_tuple(("numpy", "torch", 42)) == ("numpy", "torch")


def test_default_seed_library_order_is_stable() -> None:
    assert DEFAULT_SEED_LIBRARIES == ("numpy", "torch", "tensorflow", "random", "jax", "sklearn")