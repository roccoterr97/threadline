"""The morning summary: what it says, and the words it says it in.

:mod:`~tracker.services.summary.builder` reads the database and decides what the
summary contains; :mod:`~tracker.services.summary.renderer` turns that into a
subject line and two bodies; :mod:`~tracker.services.summary.problem_messages`
turns an error code into a sentence the owner can act on. No message text ever
enters any of the three.
"""
