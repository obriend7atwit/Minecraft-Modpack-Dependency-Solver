from dataclasses import dataclass

from modpack_solver.final_reports.statistics import cluster_bootstrap_metric


@dataclass
class Item:
    family: str
    value: float


def test_cluster_bootstrap_is_deterministic_and_bounded():
    values = [
        Item("a", 1.0),
        Item("a", 1.0),
        Item("b", 0.0),
        Item("c", 1.0),
    ]
    kwargs = {
        "family_id_getter": lambda item: item.family,
        "metric": lambda items: sum(item.value for item in items) / len(items),
        "repetitions": 250,
        "seed": 12,
    }
    first = cluster_bootstrap_metric(values, **kwargs)
    second = cluster_bootstrap_metric(values, **kwargs)
    assert first == second
    assert first.lower <= first.estimate <= first.upper
    assert 0 <= first.lower <= first.upper <= 1


def test_empty_bootstrap_is_safe():
    result = cluster_bootstrap_metric(
        [],
        family_id_getter=lambda item: item.family,
        metric=lambda _items: 0.0,
    )
    assert result.estimate == result.lower == result.upper == 0.0
