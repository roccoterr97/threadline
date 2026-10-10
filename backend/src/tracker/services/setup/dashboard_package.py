"""The dashboard as it is published: checked, given its settings, zipped again.

The prebuilt dashboard comes from a GitHub Release as one zip and a SHA-256.
Before anything from it is published, this module checks the checksum and
reads the zip in memory only: nothing is extracted to disk and nothing in it
is run. A file whose name would land outside the site (an absolute path,
``..``, a drive letter, a backslash) or that is a link refuses the whole zip,
as does one that unpacks into far more than it weighs.

Then ``config.js`` is added, holding the only two values the browser needs —
the project address and the publishable key, both public by design — and the
files are zipped again, in memory, for the host. Netlify's ``_headers`` (the
content security policy) and ``_redirects`` are never taken from the download:
the set-up writes its own copies, kept in ``netlify_site/`` beside this module
and checked against the dashboard's source by a test.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import re
import stat
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from tracker.domain.dashboard_link import require_public_key
from tracker.services.setup import values
from tracker.shared.constants.dashboard import (
    ARCHIVE_MAX_FILES,
    ARCHIVE_MAX_UNPACKED_BYTES,
    ARCHIVE_TIMESTAMP,
    BUILD_INFO_FILE,
    CONFIG_FILE,
    CONFIG_GLOBAL,
    HOSTING_FILES,
    INDEX_FILE,
)
from tracker.shared.errors import DashboardPackageError

_COMMIT: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_MIGRATION_NAME: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_SHA256_HEX: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
#: A path inside the site: parts of letters, digits and ``_.-@+~``, joined by ``/``.
_SAFE_PART: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_.@+~-]+$")
#: Files of the download that are never published as they came: the set-up writes
#: its own rule files, and the build info is only read.
_REPLACED: Final[frozenset[str]] = frozenset({*HOSTING_FILES, BUILD_INFO_FILE})
#: Where the set-up's own ``_headers`` and ``_redirects`` are kept.
_HOSTING_DIRECTORY: Final[Path] = Path(__file__).resolve().parent / "netlify_site"
_PARENT_PARTS: Final[frozenset[str]] = frozenset({".", ".."})
_ENCRYPTED_FLAG: Final[int] = 0x1
_FILE_TYPE_SHIFT: Final[int] = 16
#: The permissions every file of the new zip gets: readable, not runnable.
_FILE_MODE: Final[int] = stat.S_IFREG | 0o644


@dataclass(frozen=True, slots=True)
class BrowserSettings:
    """The two public values the dashboard reads from ``config.js``.

    Attributes:
        supabase_url: ``https://<project-ref>.supabase.co``.
        publishable_key: The publishable ("anon") key, never the secret one.
    """

    supabase_url: str
    publishable_key: str


@dataclass(frozen=True, slots=True)
class BuildInfo:
    """What the release workflow records about a dashboard it built.

    Attributes:
        commit: The commit of the template the dashboard was built from.
        latest_migration: The newest database file (``0017_daily_start``) in that commit.
    """

    commit: str
    latest_migration: str


def verify_checksum(archive: bytes, checksum_file: bytes) -> None:
    """Check the archive against the SHA-256 published beside it.

    Args:
        archive: The downloaded zip.
        checksum_file: The ``.sha256`` file: the hex digest, optionally followed
            by the file name, as ``sha256sum`` writes it.

    Raises:
        DashboardPackageError: If the file holds no digest or the digest differs.
    """
    words = checksum_file.decode("ascii", errors="replace").split()
    expected = words[0].lower() if words else ""
    if not _SHA256_HEX.match(expected):
        message = "the dashboard's checksum file holds no SHA-256"
        raise DashboardPackageError(message)
    actual = hashlib.sha256(archive).hexdigest()
    if not hmac.compare_digest(actual, expected):
        message = "the downloaded dashboard does not match its checksum - run the step again"
        raise DashboardPackageError(message)


def read_archive(archive: bytes) -> dict[str, bytes]:
    """Read every file of a zip in memory, refusing anything unsafe.

    Args:
        archive: The zip.

    Returns:
        Each file by its path inside the site.

    Raises:
        DashboardPackageError: If the zip is damaged, too large, or holds an
            unsafe entry.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            entries = [entry for entry in bundle.infolist() if not entry.is_dir()]
            _check_entries(entries)
            return _read_entries(bundle, entries)
    except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError) as error:
        message = "the downloaded dashboard is not a readable zip"
        raise DashboardPackageError(message) from error


def build_info(files: Mapping[str, bytes]) -> BuildInfo | None:
    """Read the dashboard's ``build-info.json``, if it holds one in the expected shape.

    Args:
        files: The built site, each file by its path.

    Returns:
        What it was built from; ``None`` when the file is missing or is not what
        the release workflow writes (it is a courtesy, never a reason to refuse).
    """
    content = files.get(BUILD_INFO_FILE)
    if content is None:
        return None
    try:
        record = json.loads(content)
    except ValueError:
        return None
    if not isinstance(record, dict):
        return None
    commit, migration = record.get("commit"), record.get("latestMigration")
    if not (isinstance(commit, str) and isinstance(migration, str)):
        return None
    if not (_COMMIT.match(commit) and _MIGRATION_NAME.match(migration)):
        return None
    return BuildInfo(commit=commit, latest_migration=migration)


def config_script(settings: BrowserSettings) -> bytes:
    """Write ``config.js``: the two public values, and nothing else.

    Args:
        settings: The project address and the publishable key.

    Returns:
        The file's content.

    Raises:
        ValidationFailedError: If the address is not a project address, or the
            key is empty, not plain text or a secret key.
    """
    values.project_ref(settings.supabase_url)
    key = require_public_key(values.non_empty(settings.publishable_key, "the publishable key"))
    payload = json.dumps(
        {"supabaseUrl": settings.supabase_url.rstrip("/"), "supabaseAnonKey": key},
        ensure_ascii=True,
    )
    return f"window.{CONFIG_GLOBAL} = Object.freeze({payload});\n".encode("ascii")


def publishable_archive(files: Mapping[str, bytes], settings: BrowserSettings) -> bytes:
    """Check a built site, give it its ``config.js`` and Netlify's rules, and zip it.

    Any ``_headers`` or ``_redirects`` in ``files`` is replaced by the set-up's own.

    Args:
        files: The built site, each file by its path (from the release or a local build).
        settings: The two public values the page needs.

    Returns:
        The zip to publish.

    Raises:
        DashboardPackageError: If the site is unsafe, too large, has no
            ``index.html`` or already has a ``config.js``.
        ValidationFailedError: If the settings are not usable in the browser.
    """
    _check_site(files)
    own = {name: content for name, content in files.items() if name not in _REPLACED}
    site = {**own, **hosting_files(), CONFIG_FILE: config_script(settings)}
    _check_complete(site)
    return pack(site)


def hosting_files() -> dict[str, bytes]:
    """Read the set-up's own ``_headers`` and ``_redirects``.

    Returns:
        Each file by its name in the site.

    Raises:
        DashboardPackageError: If one is missing or empty, since a site without
            its security headers must never be published.
    """
    return {name: _hosting_file(name) for name in HOSTING_FILES}


def pack(files: Mapping[str, bytes]) -> bytes:
    """Zip files in memory, in name order with a fixed date, so equal files zip alike.

    Args:
        files: Each file by its path.

    Returns:
        The zip.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in sorted(files):
            entry = zipfile.ZipInfo(name, date_time=ARCHIVE_TIMESTAMP)
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = _FILE_MODE << _FILE_TYPE_SHIFT
            bundle.writestr(entry, files[name])
    return buffer.getvalue()


def _hosting_file(name: str) -> bytes:
    """Read one of the set-up's own rule files, refusing a missing or empty one."""
    try:
        content = (_HOSTING_DIRECTORY / name).read_bytes()
    except OSError as error:
        message = f"the set-up's own {name} file is missing - download Threadline again"
        raise DashboardPackageError(message) from error
    if not content.strip():
        message = f"the set-up's own {name} file is empty - download Threadline again"
        raise DashboardPackageError(message)
    return content


def _check_entries(entries: list[zipfile.ZipInfo]) -> None:
    """Refuse a zip with too many files, unsafe names, links or encrypted parts."""
    if len(entries) > ARCHIVE_MAX_FILES:
        message = f"the dashboard holds more than {ARCHIVE_MAX_FILES} files"
        raise DashboardPackageError(message)
    for entry in entries:
        _safe_path(entry.filename)
        if stat.S_ISLNK(entry.external_attr >> _FILE_TYPE_SHIFT):
            message = f"the dashboard holds a link, {entry.filename}"
            raise DashboardPackageError(message)
        if entry.flag_bits & _ENCRYPTED_FLAG:
            message = f"the dashboard holds an encrypted file, {entry.filename}"
            raise DashboardPackageError(message)


def _read_entries(bundle: zipfile.ZipFile, entries: list[zipfile.ZipInfo]) -> dict[str, bytes]:
    """Read the files, stopping as soon as they unpack past the limit.

    The sizes a zip declares can lie, so each file is read with the room left
    plus one byte: reading more than that proves the zip is too large.
    """
    files: dict[str, bytes] = {}
    room = ARCHIVE_MAX_UNPACKED_BYTES
    for entry in entries:
        if entry.filename in files:
            message = f"the dashboard holds {entry.filename} twice"
            raise DashboardPackageError(message)
        with bundle.open(entry) as source:
            content = source.read(room + 1)
        room -= len(content)
        if room < 0:
            message = f"the dashboard unpacks into more than {ARCHIVE_MAX_UNPACKED_BYTES} bytes"
            raise DashboardPackageError(message)
        files[entry.filename] = content
    return files


def _check_site(files: Mapping[str, bytes]) -> None:
    """Refuse a site that is unsafe, too large, incomplete or already configured."""
    if len(files) > ARCHIVE_MAX_FILES:
        message = f"the dashboard holds more than {ARCHIVE_MAX_FILES} files"
        raise DashboardPackageError(message)
    for name in files:
        _safe_path(name)
    if sum(len(content) for content in files.values()) > ARCHIVE_MAX_UNPACKED_BYTES:
        message = f"the dashboard is larger than {ARCHIVE_MAX_UNPACKED_BYTES} bytes"
        raise DashboardPackageError(message)
    if INDEX_FILE not in files:
        message = f"the dashboard has no {INDEX_FILE}"
        raise DashboardPackageError(message)
    if CONFIG_FILE in files:
        message = f"the dashboard already holds a {CONFIG_FILE}; the set-up writes its own"
        raise DashboardPackageError(message)


def _check_complete(site: Mapping[str, bytes]) -> None:
    """Refuse a site that is about to be published without its page, config or rules."""
    for name in (INDEX_FILE, CONFIG_FILE, *HOSTING_FILES):
        if name not in site:
            message = f"the dashboard to publish has no {name}"
            raise DashboardPackageError(message)


def _safe_path(name: str) -> None:
    """Refuse a name that is absolute, climbs out of the site or is not plain."""
    parts = name.split("/")
    if any(part in _PARENT_PARTS or not _SAFE_PART.match(part) for part in parts):
        message = f"the dashboard holds a file outside the site or with an odd name: {name!r}"
        raise DashboardPackageError(message)
