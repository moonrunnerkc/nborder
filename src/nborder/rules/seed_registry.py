from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PatternKind = Literal["attribute_prefix", "attribute_exact", "sklearn_random_state"]


@dataclass(frozen=True, slots=True)
class CallPattern:
    """A library-relative call pattern used by NB103."""

    kind: PatternKind
    suffixes: tuple[str, ...]
    excluded_suffixes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SeedProbe:
    """Registry entry for one stochastic library."""

    library: str
    import_modules: tuple[str, ...]
    stochastic_patterns: tuple[CallPattern, ...]
    seed_patterns: tuple[CallPattern, ...]
    injection_template: str | None
    diagnostic_message: str


# NumPy accepts the legacy global seed API as already seeded, but the fixer only
# injects the modern Generator API. That keeps old notebooks quiet without adding
# new global RNG state to fixed notebooks.
SEED_PROBES: tuple[SeedProbe, ...] = (
    SeedProbe(
        library="numpy",
        import_modules=("numpy", "numpy.random"),
        stochastic_patterns=(CallPattern("attribute_prefix", ("random",)),),
        seed_patterns=(
            CallPattern("attribute_exact", ("random.seed", "random.default_rng")),
            CallPattern("attribute_exact", ("seed", "default_rng")),
        ),
        injection_template="rng = np.random.default_rng(SEED)",
        diagnostic_message="NumPy random API used before a seed is set.",
    ),
    SeedProbe(
        library="random",
        import_modules=("random",),
        stochastic_patterns=(
            CallPattern("attribute_prefix", ("",), excluded_suffixes=("SystemRandom", "seed")),
        ),
        seed_patterns=(CallPattern("attribute_exact", ("seed",)),),
        injection_template="random.seed(SEED)",
        diagnostic_message="stdlib random API used before a seed is set.",
    ),
    SeedProbe(
        library="torch",
        import_modules=("torch",),
        stochastic_patterns=(
            CallPattern(
                "attribute_prefix",
                ("rand", "randn", "randint", "normal", "bernoulli", "distributions"),
            ),
        ),
        seed_patterns=(CallPattern("attribute_exact", ("manual_seed",)),),
        injection_template="torch.manual_seed(SEED)",
        diagnostic_message="PyTorch stochastic API used before a seed is set.",
    ),
    SeedProbe(
        library="tensorflow",
        import_modules=("tensorflow",),
        stochastic_patterns=(CallPattern("attribute_prefix", ("random",)),),
        seed_patterns=(CallPattern("attribute_exact", ("random.set_seed",)),),
        injection_template="tf.random.set_seed(SEED)",
        diagnostic_message="TensorFlow random API used before a seed is set.",
    ),
    SeedProbe(
        library="jax",
        import_modules=("jax",),
        stochastic_patterns=(CallPattern("attribute_prefix", ("random",)),),
        seed_patterns=(),
        injection_template=None,
        diagnostic_message=(
            "JAX random API used without explicit PRNGKey plumbing. "
            "Thread a jax.random.PRNGKey through stochastic calls."
        ),
    ),
    SeedProbe(
        library="sklearn",
        import_modules=("sklearn",),
        stochastic_patterns=(CallPattern("sklearn_random_state", ("",)),),
        seed_patterns=(),
        injection_template=None,
        diagnostic_message=(
            "scikit-learn estimator uses random_state=None. "
            "Pass a deterministic random_state value."
        ),
    ),
)


def enabled_seed_probes(libraries: tuple[str, ...]) -> tuple[SeedProbe, ...]:
    """Return registry entries enabled by configuration.

    Args:
        libraries: Canonical library names enabled for NB103.

    Returns:
        Matching seed registry entries in stable order.
    """
    enabled_libraries = frozenset(libraries)
    return tuple(probe for probe in SEED_PROBES if probe.library in enabled_libraries)