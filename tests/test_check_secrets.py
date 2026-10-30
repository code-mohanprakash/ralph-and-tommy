import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "check_secrets.py"

# Built in pieces so this test file doesn't contain a key-shaped string itself.
# Otherwise the scanner would block this file from being committed.
FAKE_KEY = "sk-ant-" + "api03-" + "x" * 40


def scan(*paths: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, paths)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_file_with_a_key_is_blocked(tmp_path: Path) -> None:
    leaky = tmp_path / "settings.py"
    leaky.write_text(f'client = Anthropic(api_key="{FAKE_KEY}")\n')

    result = scan(leaky)

    assert result.returncode == 1
    assert f"{leaky}:1:" in result.stdout


def test_the_key_itself_is_never_printed(tmp_path: Path) -> None:
    leaky = tmp_path / "notes.txt"
    leaky.write_text(f"my key is {FAKE_KEY}\n")

    result = scan(leaky)

    # Check it was blocked first, or this test would pass with no scanner at all.
    assert result.returncode == 1
    assert FAKE_KEY not in result.stdout + result.stderr


def test_a_key_pasted_after_the_variable_name_is_blocked(tmp_path: Path) -> None:
    leaky = tmp_path / "config.env"
    leaky.write_text("ANTHROPIC_API_KEY=" + "a1b2c3" * 5 + "\n")

    assert scan(leaky).returncode == 1


def test_a_clean_file_passes(tmp_path: Path) -> None:
    clean = tmp_path / "clean.py"
    clean.write_text('model = "claude-sonnet-5-5"\n')

    assert scan(clean).returncode == 0


def test_the_empty_example_file_passes() -> None:
    assert scan(ROOT / ".env.example").returncode == 0
