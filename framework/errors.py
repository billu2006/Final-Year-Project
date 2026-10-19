"""Errors that the BT396 command-line entry point can explain to students."""


class UserInputError(Exception):
    """An invalid command-line option, configuration, or strategy selection."""


class StrategySetupError(Exception):
    """A strategy failed during construction or start()."""
