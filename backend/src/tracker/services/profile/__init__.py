"""The owner's profile: reading it, writing it to the database, rendering the guide.

A profile file is configuration the owner edits by hand, so every problem in it
is reported as one :class:`~tracker.shared.errors.ConfigurationError` naming
the field, never as a traceback.
"""
