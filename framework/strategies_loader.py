# framework/strategies_loader.py
# Loader that lets students write plain Backtrader strategies:
#
#    class TeamStrategy(bt.Strategy):
#        params = dict(...)  # or tuple-of-tuples
#
# Returns a class that always enforces COMP396 rules by wrapping the
# student class with (COMP396Base, StudentClass). We do NOT touch/parse
# the student's params; we only add ('_comp396', None) on the wrapper,
# and let Backtrader's metaclass merge params across bases.

import importlib
import inspect
import difflib
from pathlib import Path
import backtrader as bt
from framework.strategy_base import COMP396Base
from framework.errors import UserInputError, StrategySetupError

def _wrap_with_comp396(student_cls: type) -> type:
    # capture student hooks
    student_init = getattr(student_cls, "__init__", None)
    student_start = getattr(student_cls, "start", None)
    student_next = getattr(student_cls, "next", None)
    student_prenext = getattr(student_cls, "prenext", None)
    student_nextstart = getattr(student_cls, "nextstart", None)
    student_notify = getattr(student_cls, "notify_order", None)

    class Wrapped(COMP396Base, student_cls):
        # Dynamic wrapper that injects COMP396Base behaviour
        # around the student Strategy to enforce course trading rules transparently.
        # only add framework param; BT merges with student's params
        params = (("_comp396", None),)

        def __init__(self, *args, **kwargs):
            # Ensure Backtrader + mixins init
            try:
                super().__init__(*args, **kwargs)
                # Explicitly run student's __init__ so attributes like _sent/_b are set
                if callable(student_init):
                    # Backtrader has already handled the strategy parameters.
                    student_init(self)
            except Exception as exc:
                raise StrategySetupError(
                    f"Strategy initialisation failed: {type(exc).__name__}: {exc}"
                ) from exc

        def start(self):
            # COMP396 engine first
            COMP396Base.start(self)
            # then student's start
            if callable(student_start):
                try:
                    student_start(self)
                except Exception as exc:
                    raise StrategySetupError(
                        f"Strategy start() failed: {type(exc).__name__}: {exc}"
                    ) from exc

        def next(self):
            # engine first (bankruptcy, final-day, EOD limit cancels)
            allowed = COMP396Base.next(self)
            # then student's trading logic (queues market orders)
            if allowed and callable(student_next):
                student_next(self)
            # finally, flush buffered market orders this bar
            if hasattr(self, "_flush_pending_market_orders"):
                self._flush_pending_market_orders()

        def prenext(self):
            allowed = COMP396Base.next(self)
            if allowed and callable(student_prenext):
                student_prenext(self)
            self._flush_pending_market_orders()

        def nextstart(self):
            # The default hook dispatches to our gated next(). A custom hook
            # needs the same gate on the first fully warmed-up bar.
            if student_nextstart is bt.Strategy.nextstart:
                self.next()
                return
            allowed = COMP396Base.next(self)
            if allowed and callable(student_nextstart):
                student_nextstart(self)
            self._flush_pending_market_orders()

        def notify_order(self, order):
            # Log fills; BT396Broker has already charged execution costs
            COMP396Base.notify_order(self, order)
            # then student's notify
            if callable(student_notify):
                student_notify(self, order)

    Wrapped.__name__ = f"{student_cls.__name__}__COMP396Wrapped"
    return Wrapped



def load_strategy_class(module_name: str, explicit_class: str | None):
    """
    Import strategies.<module_name>, find a Backtrader Strategy class,
    and return a class that is guaranteed to enforce COMP396 rules.

    - If the found class already subclasses COMP396Base, return it as-is.
    - Otherwise, return a dynamic wrapper that injects COMP396Base behavior.
    """
    if not isinstance(module_name, str) or not module_name.isidentifier():
        raise UserInputError(
            "--strategy must be a Python filename without its folder or .py extension."
        )
    full_name = f"strategies.{module_name}"
    try:
        mod = importlib.import_module(full_name)
    except ModuleNotFoundError as exc:
        if exc.name in {full_name, "strategies"}:
            folder = Path(__file__).resolve().parent.parent / "strategies"
            available = sorted(p.stem for p in folder.glob("*.py")
                               if p.stem.isidentifier() and not p.stem.startswith("_"))
            matches = difflib.get_close_matches(module_name, available, n=3)
            hint = f"\nDid you mean: {', '.join(matches)}?" if matches else ""
            raise UserInputError(
                f"Strategy '{module_name}' was not found.\n"
                f"Expected file: {folder / (module_name + '.py')}\n"
                "Check the filename, folder, and whether Windows added .txt."
                f"{hint}"
            ) from exc
        # A strategy may exist but import a missing dependency. Preserve that distinction.
        raise UserInputError(
            f"Strategy '{module_name}' could not be imported: "
            f"dependency '{exc.name}' was not found.\n"
            "Check its imports and install the required package in the active environment."
        ) from exc

    # pick the class
    if explicit_class:
        cls = getattr(mod, explicit_class, None)
        if not inspect.isclass(cls) or not issubclass(cls, bt.Strategy):
            raise UserInputError(
                f"'{explicit_class}' is not a Backtrader Strategy class in '{module_name}'."
            )
    else:
        candidates = [obj for _, obj in inspect.getmembers(mod, inspect.isclass)
                      if obj is not bt.Strategy and issubclass(obj, bt.Strategy)
                      and obj.__module__ == mod.__name__]
        team_class = getattr(mod, "TeamStrategy", None)
        if team_class in candidates:
            cls = team_class
        elif len(candidates) == 1:
            cls = candidates[0]
        elif not candidates:
            raise UserInputError(f"No Backtrader Strategy class defined in '{module_name}'.")
        else:
            raise UserInputError(
                f"Multiple Strategy classes defined in '{module_name}'. "
                "Select one with --strategy-class.\n"
                f"Available classes: {', '.join(c.__name__ for c in candidates)}"
            )

    if issubclass(cls, COMP396Base):
        return cls

    return _wrap_with_comp396(cls)


def validate_strategy_params(strategy_cls, params: dict) -> None:
    # Reject misspelled and reserved CLI names before constructing the strategy.
    allowed = {name for name in strategy_cls.params._getkeys()
               if not name.startswith('_')}
    unknown = sorted(set(params) - allowed)
    if unknown:
        hints = []
        for name in unknown:
            matches = difflib.get_close_matches(name, sorted(allowed), n=1)
            if matches:
                hints.append(f"Did you mean '{matches[0]}' instead of '{name}'?")
        raise UserInputError(
            f"Unknown or reserved strategy parameter(s): {', '.join(unknown)}.\n"
            f"Valid parameters: {', '.join(sorted(allowed)) or '(none)'}."
            + ("\n" + "\n".join(hints) if hints else "")
        )
