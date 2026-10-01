"""Operational tuning values, one module per concern.

These are not deployment settings: they never belong in ``.env``. Anything that
changes per machine or holds a secret goes through
:func:`tracker.shared.config.get_settings` instead.
"""
