import subprocess
import sys


def test_basic_repair_example_runs_end_to_end():
    completed = subprocess.run(
        [sys.executable, "examples/basic_repair.py"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "Repair plan found" in completed.stdout
    assert "Total weighted cost: 1" in completed.stdout
