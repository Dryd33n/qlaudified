import importlib
import pkgutil

import qlaudified
from qlaudified.backends import get_backend
from qlaudified.lexicon import HEDGES, STRENGTH_ORDER


def test_all_modules_import():
    for mod in pkgutil.walk_packages(qlaudified.__path__, "qlaudified."):
        importlib.import_module(mod.name)


def test_name_defined_once():
    assert qlaudified.NAME == "qlaudified"


def test_strength_order_covers_lexicon():
    assert sorted(STRENGTH_ORDER) == sorted(HEDGES)


def test_fake_backend_returns_canned_json():
    backend = get_backend("fake")
    backend.responses.append({"verdict": "supported"})
    assert backend.complete_json("p", {}) == {"verdict": "supported"}
    assert backend.complete_json("p", {}) is None


def test_none_backend_is_default():
    assert get_backend("none").name == "none"
    assert get_backend("unknown").name == "none"
