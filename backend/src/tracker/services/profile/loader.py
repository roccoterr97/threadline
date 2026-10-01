"""Read the owner's profile, or the default preset when there is none."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from tracker.domain.profile import Profile
from tracker.shared.constants.profile import DEFAULT_PRESET, PRESET_DIRECTORY, PROFILE_FILE
from tracker.shared.errors import ConfigurationError

#: A preset name also becomes a file name, so it may hold nothing else.
_PRESET_NAME: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z_]{0,40}$")

#: Extension of every profile and preset file.
PROFILE_SUFFIX: Final[str] = ".toml"


@dataclass(frozen=True, slots=True)
class LoadedProfile:
    """A validated profile and where it came from.

    Attributes:
        profile: The profile.
        source: The file it was read from.
        is_default: True when the owner has neither a profile file nor a
            chosen preset, and the default preset stands in for them.
    """

    profile: Profile
    source: Path
    is_default: bool


def load_profile(
    profile_file: Path = PROFILE_FILE,
    preset_directory: Path = PRESET_DIRECTORY,
    chosen_preset: str | None = None,
) -> LoadedProfile:
    """Read the owner's profile: their file, else the preset they chose, else the default.

    Args:
        profile_file: The owner's own profile.
        preset_directory: Where the shipped presets live.
        chosen_preset: The preset the owner chose with ``tracker profile
            choose``, as the database remembers it.

    Returns:
        The profile, with where it came from.

    Raises:
        ConfigurationError: If the file that is read is not a valid profile,
            or the chosen preset no longer exists.
    """
    if profile_file.is_file():
        return LoadedProfile(read_profile(profile_file), profile_file, is_default=False)
    preset = chosen_preset or DEFAULT_PRESET
    preset_file = preset_path(preset, preset_directory)
    return LoadedProfile(read_profile(preset_file), preset_file, is_default=chosen_preset is None)


def preset_path(name: str, preset_directory: Path = PRESET_DIRECTORY) -> Path:
    """Return the file of one shipped preset.

    Args:
        name: The preset's name, such as ``sales_outreach``.
        preset_directory: Where the shipped presets live.

    Returns:
        The preset's file.

    Raises:
        ConfigurationError: If the name is malformed or no such preset exists.
    """
    path = preset_directory / f"{name}{PROFILE_SUFFIX}"
    if not _PRESET_NAME.fullmatch(name) or not path.is_file():
        message = f"no preset named '{name}'; choose one of: {', '.join(preset_names())}"
        raise ConfigurationError(message)
    return path


def preset_names(preset_directory: Path = PRESET_DIRECTORY) -> tuple[str, ...]:
    """List the shipped presets.

    Args:
        preset_directory: Where the shipped presets live.

    Returns:
        The preset names, alphabetically.
    """
    return tuple(sorted(path.stem for path in preset_directory.glob(f"*{PROFILE_SUFFIX}")))


def read_profile(path: Path) -> Profile:
    """Read and validate one profile file.

    Args:
        path: The TOML file.

    Returns:
        The validated profile.

    Raises:
        ConfigurationError: If the file cannot be read, is not TOML, or does
            not describe a valid profile. The message names the file and every
            field at fault.
    """
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except FileNotFoundError as error:
        message = f"{path.name}: file not found"
        raise ConfigurationError(message) from error
    except tomllib.TOMLDecodeError as error:
        message = f"{path.name} is not valid TOML: {error}"
        raise ConfigurationError(message) from error
    try:
        return Profile.model_validate(raw)
    except ValidationError as error:
        message = f"{path.name} is not a valid profile: {describe_problems(error)}"
        raise ConfigurationError(message) from error


def describe_problems(error: ValidationError) -> str:
    """Turn a validation failure into one line an owner can act on.

    The profile is the owner's own file, not untrusted input, so the reason
    Pydantic gives is included next to each field.

    Args:
        error: The failure.

    Returns:
        ``field: reason`` pairs separated by semicolons.
    """
    return "; ".join(
        f"{'.'.join(str(part) for part in item['loc']) or 'profile'}: {item['msg']}"
        for item in error.errors()
    )
