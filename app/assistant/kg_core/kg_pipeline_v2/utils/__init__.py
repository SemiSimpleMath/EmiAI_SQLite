"""
Utilities for KG Pipeline V2

Shared utilities for thread-safe operations, data waiting, and coordination.
"""

from .thread_safe_waiting import (
    ThreadSafeDataWaiter,
    wait_for_stage_data
)

__all__ = [
    'ThreadSafeDataWaiter',
    'wait_for_stage_data'
]
