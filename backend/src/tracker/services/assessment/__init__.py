"""The assessment: preparing work for the assistant and checking what comes back.

Python never calls an AI service. It writes a batch file describing a few
people, a Claude Code session reads that file and writes a verdict file, and
Python validates the verdict file before anything reaches the database.
"""
