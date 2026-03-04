"""
debug_bundle.py — Serialise negotiation run details to JSON for post-hoc
debugging and replay analysis.

Provides:
    DebugBundle       – dataclass holding all run metadata
    build_bundle_from_negotiation – factory that creates a bundle from a
                                     ScenarioDef + NegotiationResult
    save_bundle       – write a bundle to disk as pretty-printed JSON
"""

from __future__ import annotations

import json
import dataclasses
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
#  DATA CLASS
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class DebugBundle:
    """All information about a single negotiation run."""

    # ── identity ────────────────────────────────────────────────────────
    timestamp: str = ""
    seed: int | None = None

    # ── scenario ────────────────────────────────────────────────────────
    domain: str = ""
    task_type: str = ""
    difficulty: str = ""
    n_issues: int = 0
    n_outcomes: int = 0
    opposition: float = 0.0
    conflict: float = 0.0
    n_pareto: int = 0

    # ── agents ──────────────────────────────────────────────────────────
    agent_a_name: str = ""
    agent_b_name: str = ""

    # ── outcome ─────────────────────────────────────────────────────────
    agreement: Any = None
    n_steps_taken: int = 0
    n_steps_allowed: int = 0
    timedout: bool = False
    broken: bool = False
    error: str = ""
    wall_seconds: float = 0.0

    # ── utilities ───────────────────────────────────────────────────────
    util_a: float | None = None
    util_b: float | None = None
    welfare: float | None = None
    nash_product: float | None = None
    pareto_dist: float | None = None
    pareto_optimality: float | None = None
    nash_optimality: float | None = None
    kalai_optimality: float | None = None
    max_welfare_opt: float | None = None

    # ── extra (free-form) ───────────────────────────────────────────────
    extra: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════
#  BUILDER
# ═══════════════════════════════════════════════════════════════════════════

def build_bundle_from_negotiation(
    scenario,
    result,
    *,
    mechanism=None,
    seed: int | None = None,
) -> DebugBundle:
    """
    Create a DebugBundle from a ScenarioDef and NegotiationResult.

    Parameters
    ----------
    scenario : ScenarioDef
        The scenario that was negotiated.
    result : NegotiationResult
        The outcome of the negotiation.
    mechanism : SAOMechanism, optional
        If supplied, extra mechanism state is captured.
    seed : int, optional
        The RNG seed used for the evaluation run.
    """
    # Convert agreement to something JSON-serialisable
    agreement_ser = None
    if result.agreement is not None:
        try:
            agreement_ser = dict(result.agreement)
        except (TypeError, ValueError):
            agreement_ser = str(result.agreement)

    bundle = DebugBundle(
        timestamp=datetime.now(timezone.utc).isoformat(),
        seed=seed,
        domain=result.domain,
        task_type=getattr(result, "task_type", ""),
        difficulty=getattr(result, "difficulty", ""),
        n_issues=len(getattr(scenario, "issues", [])),
        n_outcomes=getattr(result, "n_outcomes", 0),
        opposition=getattr(result, "opposition", 0.0),
        conflict=getattr(scenario, "conflict", 0.0),
        n_pareto=getattr(scenario, "n_pareto", 0),
        agent_a_name=result.agent_a_name,
        agent_b_name=result.agent_b_name,
        agreement=agreement_ser,
        n_steps_taken=result.n_steps_taken,
        n_steps_allowed=result.n_steps_allowed,
        timedout=result.timedout,
        broken=result.broken,
        error=result.error,
        wall_seconds=result.wall_seconds,
        util_a=result.util_a,
        util_b=result.util_b,
        welfare=result.welfare,
        nash_product=result.nash_product,
        pareto_dist=result.pareto_dist,
        pareto_optimality=result.pareto_optimality,
        nash_optimality=result.nash_optimality,
        kalai_optimality=result.kalai_optimality,
        max_welfare_opt=result.max_welfare_opt,
    )

    # Capture mechanism trace if available
    if mechanism is not None:
        extra: dict[str, Any] = {}
        try:
            state = mechanism.state
            extra["mechanism_step"] = getattr(state, "step", None)
            extra["mechanism_running"] = getattr(state, "running", None)
            # Offer history
            history = getattr(mechanism, "history", None)
            if history is not None:
                # Keep last 50 offers at most to bound file size
                offers = []
                for item in history[-50:]:
                    try:
                        offers.append(str(item))
                    except Exception:
                        offers.append(repr(item))
                extra["last_offers"] = offers
        except Exception:
            pass
        bundle.extra = extra

    return bundle


# ═══════════════════════════════════════════════════════════════════════════
#  SERIALISATION
# ═══════════════════════════════════════════════════════════════════════════

def _default_serialiser(obj):
    """Fallback JSON serialiser for non-standard types."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, Path):
        return str(obj)
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
    return str(obj)


def save_bundle(bundle: DebugBundle, path: Path | str) -> None:
    """Write a DebugBundle to *path* as prettified JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(bundle)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=_default_serialiser)
