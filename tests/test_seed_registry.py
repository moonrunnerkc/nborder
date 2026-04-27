from __future__ import annotations

from nborder.rules.seed_registry import SEED_PROBES, enabled_seed_probes


def test_seed_registry_contains_all_phase4_libraries() -> None:
    library_names = tuple(probe.library for probe in SEED_PROBES)

    assert library_names == ("numpy", "random", "torch", "tensorflow", "jax", "sklearn")


def test_seed_registry_marks_jax_and_sklearn_as_diagnostic_only() -> None:
    diagnostic_only = {
        probe.library
        for probe in SEED_PROBES
        if probe.injection_template is None
    }

    assert diagnostic_only == {"jax", "sklearn"}


def test_enabled_seed_probes_filters_by_configured_libraries() -> None:
    enabled = enabled_seed_probes(("numpy", "torch"))

    assert tuple(probe.library for probe in enabled) == ("numpy", "torch")


def test_numpy_registry_detects_legacy_and_injects_both_apis() -> None:
    numpy_probe = next(probe for probe in SEED_PROBES if probe.library == "numpy")
    seed_suffixes = {
        suffix
        for seed_pattern in numpy_probe.seed_patterns
        for suffix in seed_pattern.suffixes
    }

    assert "random.seed" in seed_suffixes
    assert numpy_probe.injection_template == (
        "np.random.seed(SEED)\nrng = np.random.default_rng(SEED)"
    )
