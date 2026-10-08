"""Path normalization: separators, project-relative paths, 8.3 short names, self-capture."""

import sys

import pytest

from qlaudified.paths import is_store_path, long_path, normalize, safe_name


def test_inside_the_project_becomes_relative(tmp_path):
    assert normalize(str(tmp_path / "notes" / "q3.md"), tmp_path) == "notes/q3.md"


def test_relative_paths_resolve_against_cwd(tmp_path):
    assert normalize("ledger\\config.py", tmp_path, cwd=str(tmp_path)) == "ledger/config.py"
    assert normalize("config.py", tmp_path, cwd=str(tmp_path / "ledger")) == "ledger/config.py"


def test_outside_the_project_stays_absolute_with_forward_slashes(tmp_path):
    other = tmp_path.parent / "elsewhere" / "x.md"
    out = normalize(str(other), tmp_path)
    assert "\\" not in out and out.endswith("elsewhere/x.md") and not out.startswith("x.md")


@pytest.mark.skipif(sys.platform != "win32", reason="8.3 short names are Windows-only")
def test_short_names_expand(tmp_path):
    import ctypes

    folder = tmp_path / "A Long Folder Name"
    folder.mkdir()
    (folder / "notes.md").write_text("x")
    buf = ctypes.create_unicode_buffer(32768)
    ctypes.windll.kernel32.GetShortPathNameW(str(folder / "notes.md"), buf, len(buf))
    short = buf.value
    if "~" not in short:
        pytest.skip("8.3 names are disabled on this volume")
    assert long_path(short) == str(folder / "notes.md")
    assert normalize(short, tmp_path) == "A Long Folder Name/notes.md"
    # a file that doesn't exist yet still expands through its existing parent
    assert long_path(short[: short.rindex("\\")] + "\\gone.md").endswith("A Long Folder Name\\gone.md")


def test_store_paths_are_recognized():
    assert is_store_path(".claude/.qlaudified/sessions/s/index.sqlite")
    assert is_store_path("C:/p/.claude/.qlaudified/errors.log")
    assert not is_store_path(".claude/settings.json")


def test_safe_name():
    assert safe_name("<SESSION_0>") == "_SESSION_0_"
    assert safe_name("abc-123.def") == "abc-123.def"
