"""Package with re-exports for testing __init__.py resolution."""

from .helpers import greet, compute_total
from .internal import InternalClass

__all__ = ["greet", "compute_total", "InternalClass"]
