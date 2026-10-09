"""``@record``: the dataclass slice the hooks use, and that the hook path stays free of
``dataclasses`` and ``traceback`` (NFR-3)."""

import subprocess
import sys
from pathlib import Path

import pytest

from qlaudified.records import asdict, fields, record

REPO = Path(__file__).resolve().parents[2]


@record
class Point:
    x: int
    y: int = 0
    tags: list[str] = []  # noqa: RUF012 - @record copies it per instance


@record
class Pair:
    a: Point
    b: list[Point]


def test_init_positional_keyword_and_defaults():
    assert (Point(1).x, Point(1).y) == (1, 0)
    assert Point(1, 2) == Point(y=2, x=1)
    assert Point(1) != Point(2)
    assert repr(Point(1, 2)) == "Point(x=1, y=2, tags=[])"


def test_mutable_default_is_copied_per_instance():
    a, b = Point(1), Point(2)
    a.tags.append("hedged")
    assert b.tags == [] and Point.tags == []


@pytest.mark.parametrize("args, kwargs", [((), {}), ((1, 2, [], 4), {}), ((1,), {"x": 2}),
                                          ((1,), {"z": 3})])
def test_bad_arguments_raise_type_error(args, kwargs):
    with pytest.raises(TypeError):
        Point(*args, **kwargs)


def test_required_field_after_default_is_rejected():
    with pytest.raises(TypeError):
        @record
        class Bad:
            a: int = 0
            b: int


def test_fields_and_asdict():
    assert fields(Point) == ("x", "y", "tags") == fields(Point(1))
    assert asdict(Pair(Point(1), [Point(2, tags=["a"])])) == {
        "a": {"x": 1, "y": 0, "tags": []}, "b": [{"x": 2, "y": 0, "tags": ["a"]}]}


def test_records_are_unhashable_like_dataclasses():
    with pytest.raises(TypeError):
        hash(Point(1))


@pytest.mark.parametrize("hook", ["post_tool_use", "stop", "user_prompt_submit", "session_start"])
def test_hook_path_skips_heavy_imports(hook):
    code = (f"import sys; sys.path.insert(0, {str(REPO)!r}); import qlaudified.log, "
            f"qlaudified.hooks.{hook}; print(sorted({{'dataclasses', 'traceback', 'inspect'}} "
            f"& set(sys.modules)))")
    out = subprocess.run([sys.executable, "-S", "-c", code], capture_output=True, text=True,
                         check=True).stdout.strip()
    assert out == "[]"
