"""``@record``: the slice of ``@dataclass`` the hooks use, without importing ``dataclasses`` (NFR-3).

``dataclasses`` pulls in ``inspect``, ``ast`` and ``dis``: ~27 ms of the 300 ms budget on every
hook call. Hook-path classes only need an ``__init__`` built from the annotations and defaults,
``__eq__``, ``__repr__``, ``fields()`` and ``asdict()``. A list, dict or set default is copied per
instance, as ``field(default_factory=...)`` would.
"""

TYPE_CHECKING = False  # importing typing would cost what this module saves
if TYPE_CHECKING:
    from typing import dataclass_transform
else:
    def dataclass_transform(**_):
        return lambda f: f

MUTABLE = (list, dict, set)


@dataclass_transform(eq_default=True)
def record(cls):
    names = tuple(cls.__annotations__)
    defaults = {n: cls.__dict__[n] for n in names if n in cls.__dict__}
    first_default = next((i for i, n in enumerate(names) if n in defaults), len(names))
    if any(n not in defaults for n in names[first_default:]):
        raise TypeError(f"{cls.__name__}: a field without a default follows one with a default")

    def __init__(self, *args, **kwargs):
        if len(args) > len(names):
            raise TypeError(f"{cls.__name__}() takes {len(names)} arguments, got {len(args)}")
        values = dict(zip(names, args))
        for key, value in kwargs.items():
            if key not in names:
                raise TypeError(f"{cls.__name__}() got an unexpected keyword argument {key!r}")
            if key in values:
                raise TypeError(f"{cls.__name__}() got multiple values for argument {key!r}")
            values[key] = value
        for name in names:
            if name in values:
                value = values[name]
            elif name in defaults:
                value = defaults[name]
                if isinstance(value, MUTABLE):
                    value = value.copy()
            else:
                raise TypeError(f"{cls.__name__}() missing required argument {name!r}")
            setattr(self, name, value)

    def __eq__(self, other):
        if other.__class__ is not self.__class__:
            return NotImplemented
        return all(getattr(self, n) == getattr(other, n) for n in names)

    def __repr__(self):
        return f"{cls.__name__}({', '.join(f'{n}={getattr(self, n)!r}' for n in names)})"

    cls.__init__ = __init__
    cls.__eq__ = __eq__
    cls.__hash__ = None  # mutable, like a default dataclass
    cls.__repr__ = __repr__
    cls.__record_fields__ = names
    return cls


def fields(obj_or_cls) -> tuple[str, ...]:
    """Field names, in declaration order."""
    return obj_or_cls.__record_fields__


def asdict(obj) -> dict:
    """Fields as a dict, with records inside lists and dicts converted too."""

    def convert(value):
        if hasattr(value, "__record_fields__") and not isinstance(value, type):
            return {n: convert(getattr(value, n)) for n in value.__record_fields__}
        if isinstance(value, (list, tuple)):
            return type(value)(convert(v) for v in value)
        if isinstance(value, dict):
            return {k: convert(v) for k, v in value.items()}
        return value

    return convert(obj)
