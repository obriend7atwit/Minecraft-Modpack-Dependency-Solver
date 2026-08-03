from __future__ import annotations

import pytest

from modpack_solver.analysis import measure_runtime


def test_three_repetitions_produce_three_samples() -> None:
    _, runtime = measure_runtime(lambda: "same", repetitions=3, warmup_runs=0)

    assert len(runtime.samples_seconds) == 3


def test_median_minimum_and_maximum_are_recorded() -> None:
    _, runtime = measure_runtime(lambda: "same", repetitions=3, warmup_runs=0)

    assert runtime.minimum_seconds <= runtime.median_seconds <= runtime.maximum_seconds


def test_warmup_is_not_included() -> None:
    calls = {"count": 0}

    def operation():
        calls["count"] += 1
        return "same"

    _, runtime = measure_runtime(operation, repetitions=2, warmup_runs=1)

    assert calls["count"] == 3
    assert len(runtime.samples_seconds) == 2


def test_invalid_repetition_count_fails() -> None:
    with pytest.raises(ValueError, match="repetitions"):
        measure_runtime(lambda: "same", repetitions=0)


def test_repeated_deterministic_outcomes_are_accepted() -> None:
    result, _ = measure_runtime(lambda: {"value": 1}, repetitions=2, warmup_runs=0)

    assert result == {"value": 1}


def test_different_outcomes_produce_clear_error() -> None:
    values = iter([1, 2])

    with pytest.raises(ValueError, match="different deterministic outcomes"):
        measure_runtime(lambda: next(values), repetitions=2, warmup_runs=0)


def test_runtime_samples_are_non_negative() -> None:
    _, runtime = measure_runtime(lambda: "same", repetitions=2, warmup_runs=0)

    assert all(sample >= 0 for sample in runtime.samples_seconds)
