from modpack_solver.final_dataset.validation import validate_final_dataset


def test_final_dataset_validates_fully_offline():
    result = validate_final_dataset("data/final_dataset/manifest.json", offline=True)
    assert result.passed
    assert result.total_cases >= 60
    assert result.failed_cases == 0
    assert result.size_category_counts["huge"] > 0


def test_final_dataset_validation_can_limit_cases():
    result = validate_final_dataset(
        "data/final_dataset/manifest.json", offline=True, max_cases=3
    )
    assert result.total_cases == 3
    assert result.passed_cases == 3
