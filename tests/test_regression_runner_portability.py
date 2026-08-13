from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_ai_review_regression


def test_ai_review_runner_uses_repository_local_pytest_temp(tmp_path, monkeypatch):
    commands = []

    def fake_run(command, **kwargs):
        commands.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "passed", "")

    monkeypatch.setattr(run_ai_review_regression.subprocess, "run", fake_run)
    output = tmp_path / "results"
    assert run_ai_review_regression.main(output) is False
    assert (output / "pytest-temp").is_dir()
    assert len(commands) == run_ai_review_regression.EXPECTED_CASES
    for command, kwargs in commands:
        assert "--basetemp" in command
        basetemp = Path(command[command.index("--basetemp") + 1])
        assert output in basetemp.parents
        assert kwargs["cwd"] == ROOT
