import os
from pathlib import Path
import subprocess
import sys


def test_help_works_with_windows_cyrillic_console_encoding():
    env = dict(os.environ, PYTHONIOENCODING="cp1251",
               PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    result = subprocess.run([sys.executable, "-m", "hdr_share", "--help"],
                            env=env, capture_output=True)
    assert result.returncode == 0, result.stderr.decode("cp1251", errors="replace")
    assert b"usage:" in result.stdout
