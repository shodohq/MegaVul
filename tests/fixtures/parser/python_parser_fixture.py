"""
Custom fixture for testing ParserPython edge cases.

Each function is annotated with the expected extraction behaviour so that
test assertions are easy to derive from the source.
"""

from typing import Optional


# ---------------------------------------------------------------------------
# Top-level functions (5 total)
# ---------------------------------------------------------------------------


# [1] no type annotations at all
def add(a, b):
    return a + b


# [2] full type annotations + default parameter
def greet(name: str, greeting: str = "Hello") -> str:
    return f"{greeting}, {name}!"


# [3] *args and **kwargs with a typed leading parameter
def log_event(event: str, *args, **kwargs) -> None:
    pass


# [4] outer function with a nested function.
#     outer_with_nested IS extracted; _inner is NOT (it is nested).
def outer_with_nested(n: int) -> int:
    def _inner(x):  # nested – must be excluded by the parser
        return x + 1

    return _inner(n)


# [5] top-level function with a decorator
@some_decorator  # type: ignore[name-defined]
def decorated_top_level(value: Optional[int] = None) -> bool:
    return value is not None


# ---------------------------------------------------------------------------
# Class with various method kinds (5 total, all prefixed DataProcessor.xxx)
# ---------------------------------------------------------------------------


class DataProcessor:

    # [6] __init__ – no return type annotation
    def __init__(self, config: dict):
        self.config = config

    # [7] *items variadic + keyword-only strict param
    def process(self, *items, strict: bool = False) -> list:
        if strict:
            return [i for i in items if i is not None]
        return list(items)

    # [8] @classmethod – cls is first parameter
    @classmethod
    def from_dict(cls, data: dict) -> "DataProcessor":
        return cls(data)

    # [9] @staticmethod – no self/cls
    @staticmethod
    def validate(value) -> bool:
        return value is not None

    # [10] @property (stacked decorators: just @property here)
    @property
    def name(self) -> str:
        return self.config.get("name", "")
