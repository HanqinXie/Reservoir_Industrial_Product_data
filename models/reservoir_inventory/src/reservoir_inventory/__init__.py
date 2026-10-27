"""Independent, explicitly bounded reservoir / industrial inventory prototype."""

from .model import CaseData, InputError, OptimizationError, Solution, solve, solve_comparison

__version__ = "0.1.0"
__all__ = ["CaseData", "InputError", "OptimizationError", "Solution", "solve", "solve_comparison"]
