"""Comet capture priority.

v1 stub — comets are still considered as capture targets via the regular
:mod:`targeting` pipeline (``view.is_comet(target.id)`` triggers the
``comet_value_mult`` multiplier). Dedicated comet-priority logic (preempting
other targets when ROI exceeds threshold) lands in v1.1 per spec §7.2.6.
"""

from __future__ import annotations

__all__: list[str] = []
