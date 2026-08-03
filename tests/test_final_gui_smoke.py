import subprocess
import sys


def test_final_gui_smoke_test_runs_without_display():
    completed = subprocess.run(
        [sys.executable, "-m", "modpack_solver", "--smoke-test"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "Display-free GUI smoke test passed." in completed.stdout
