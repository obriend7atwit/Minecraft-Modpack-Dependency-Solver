"""Run one deterministic repair through the complete solver pipeline."""

from modpack_solver.final_gui.presenter import analyze_loaded_case, build_result_summary, load_builtin_sample
from modpack_solver.final_gui.state import FinalGuiState


def main() -> None:
    state = FinalGuiState()
    load_builtin_sample(state, "missing_required_dependency.json")
    analyze_loaded_case(state)
    result = build_result_summary(state)
    print(result.title)
    print(result.message)
    for index, action in enumerate(result.actions, 1):
        print(f"{index}. {action}")
    print(f"Total weighted cost: {result.total_cost}")
    print(f"Original mods preserved: {result.preserved}")


if __name__ == "__main__":
    main()
