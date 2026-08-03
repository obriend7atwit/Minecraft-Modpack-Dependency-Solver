"""Deterministic family-clustered bootstrap summaries."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
import math
import random
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field


T = TypeVar("T")


class ConfidenceInterval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estimate: float
    lower: float
    upper: float
    confidence_level: float = Field(default=0.95, gt=0.0, lt=1.0)


def cluster_bootstrap_metric(
    results: Sequence[T],
    *,
    family_id_getter: Callable[[T], str],
    metric: Callable[[Sequence[T]], float],
    repetitions: int = 2000,
    seed: int = 42,
) -> ConfidenceInterval:
    """Resample whole source families and return a percentile interval.

    These intervals quantify uncertainty within the controlled corpus. They do
    not imply random sampling from the complete Minecraft modpack ecosystem.
    """

    if repetitions < 1:
        raise ValueError("repetitions must be at least 1.")
    values = list(results)
    if not values:
        return ConfidenceInterval(estimate=0.0, lower=0.0, upper=0.0)

    grouped: dict[str, list[T]] = defaultdict(list)
    for result in values:
        family_id = family_id_getter(result).strip()
        if not family_id:
            raise ValueError("Every bootstrap result must have a nonempty family ID.")
        grouped[family_id].append(result)
    family_ids = sorted(grouped)

    estimate = float(metric(values))
    rng = random.Random(seed)
    samples: list[float] = []
    for _ in range(repetitions):
        sampled: list[T] = []
        for family_id in rng.choices(family_ids, k=len(family_ids)):
            sampled.extend(grouped[family_id])
        samples.append(float(metric(sampled)))
    samples.sort()
    alpha = 0.05
    return ConfidenceInterval(
        estimate=estimate,
        lower=_percentile(samples, alpha / 2),
        upper=_percentile(samples, 1 - alpha / 2),
    )


def _percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    position = (len(values) - 1) * quantile
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return float(values[lower_index])
    fraction = position - lower_index
    return float(
        values[lower_index] * (1 - fraction)
        + values[upper_index] * fraction
    )
