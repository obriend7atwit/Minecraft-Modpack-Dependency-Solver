import pytest
from pydantic import ValidationError

from modpack_solver.final_dataset.models import (
    FinalCaseSourceType,
    FinalDatasetCaseSpec,
    FinalDatasetManifest,
    ModificationType,
)


def _case(**updates):
    payload = {
        "case_id": "case-one",
        "display_name": "Case One",
        "source_type": "synthetic",
        "fixture_path": "case.json",
        "minecraft_version": "1.20.1",
        "loader": "fabric",
        "selected_mod_count": 30,
        "pack_size_category": "small",
        "expected_initial_status": "compatible",
        "expected_solver_status": "already_compatible",
    }
    payload.update(updates)
    return FinalDatasetCaseSpec.model_validate(payload)


def test_final_case_model_validates_normal_case():
    assert _case().source_type == FinalCaseSourceType.SYNTHETIC


def test_final_case_rejects_mismatched_size_category():
    with pytest.raises(ValidationError, match="pack_size_category"):
        _case(selected_mod_count=31, pack_size_category="small")


def test_modified_real_requires_description():
    with pytest.raises(ValidationError, match="modification_description"):
        _case(source_type="modified_real", modification_type="change_loader")


def test_manifest_rejects_duplicate_case_ids():
    with pytest.raises(ValidationError, match="Duplicate"):
        FinalDatasetManifest(
            dataset_name="Dataset",
            dataset_version="1",
            description="Test",
            cases=[_case(), _case()],
        )


def test_modified_real_must_reference_known_original():
    modified = _case(
        case_id="modified",
        source_type="modified_real",
        modification_type=ModificationType.CHANGE_LOADER,
        modification_description="Changed loader.",
        original_case_id="missing-original",
    )
    with pytest.raises(ValidationError, match="unknown original_case_id"):
        FinalDatasetManifest(
            dataset_name="Dataset",
            dataset_version="1",
            description="Test",
            cases=[modified],
        )
