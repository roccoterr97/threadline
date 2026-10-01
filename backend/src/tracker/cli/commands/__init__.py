"""Command modules, discovered automatically.

Every module in this package exposes ``register(cli: typer.Typer) -> None`` and
attaches whatever commands and groups it owns. Nothing keeps a central list, so
two plans can add commands at the same time without touching the same file.
"""
