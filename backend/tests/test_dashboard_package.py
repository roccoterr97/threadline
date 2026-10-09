"""The prebuilt dashboard: its checksum, its safe unpacking in memory, its config.js."""

from __future__ import annotations

import hashlib
import io
import json
import stat
import sys
import warnings
import zipfile

import pytest

from tests.setup_world import BUILT_SITE, GOOD_PUBLISHABLE, PROJECT_URL
from tracker.services.setup import dashboard_package
from tracker.services.setup.dashboard_package import (
    BrowserSettings,
    config_script,
    pack,
    publishable_archive,
    read_archive,
    verify_checksum,
)
from tracker.shared.errors import DashboardPackageError, ValidationFailedError

SETTINGS = BrowserSettings(supabase_url=PROJECT_URL, publishable_key=GOOD_PUBLISHABLE)


def _zip(*entries: tuple[zipfile.ZipInfo | str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # a duplicate name warns while it is written
        with zipfile.ZipFile(buffer, "w") as bundle:
            for entry, content in entries:
                bundle.writestr(entry, content)
    return buffer.getvalue()


# --- Checksum -------------------------------------------------------------------


def test_a_matching_checksum_passes_in_the_form_sha256sum_writes() -> None:
    archive = pack(BUILT_SITE)
    line = f"{hashlib.sha256(archive).hexdigest().upper()}  dashboard.zip\n".encode()

    verify_checksum(archive, line)


def test_a_different_checksum_is_refused() -> None:
    archive = pack(BUILT_SITE)

    with pytest.raises(DashboardPackageError, match="does not match"):
        verify_checksum(archive, hashlib.sha256(b"other").hexdigest().encode())


@pytest.mark.parametrize("content", [b"", b"not-a-digest dashboard.zip", b"\xff\xfe"])
def test_a_checksum_file_without_a_digest_is_refused(content: bytes) -> None:
    with pytest.raises(DashboardPackageError, match="holds no SHA-256"):
        verify_checksum(pack(BUILT_SITE), content)


# --- Reading the zip ------------------------------------------------------------


def test_a_good_zip_reads_back_every_file_and_skips_folders() -> None:
    archive = _zip(("assets/", b""), *BUILT_SITE.items())

    assert read_archive(archive) == BUILT_SITE


@pytest.mark.parametrize(
    "name",
    [
        "../outside.js",
        "assets/../../outside.js",
        "/etc/passwd",
        "./index.html",
        "assets//double.js",
        "C:/Windows/evil.js",
        pytest.param(
            "assets\\evil.js",
            marks=pytest.mark.skipif(
                sys.platform == "win32",
                reason="Python's zipfile reads a backslash as a folder separator on Windows, "
                "so this name arrives as the harmless assets/evil.js",
            ),
        ),
        "with space.js",
    ],
)
def test_a_name_outside_the_site_or_odd_is_refused(name: str) -> None:
    with pytest.raises(DashboardPackageError, match="outside the site"):
        read_archive(_zip((name, b"x"), *BUILT_SITE.items()))


def test_a_link_is_refused() -> None:
    link = zipfile.ZipInfo("assets/link.js")
    link.external_attr = (stat.S_IFLNK | 0o777) << 16

    with pytest.raises(DashboardPackageError, match="link"):
        read_archive(_zip((link, b"/etc/passwd"), *BUILT_SITE.items()))


def _marked_encrypted(archive: bytes, name: str) -> bytes:
    """Set the "encrypted" flag of one file in the zip's central directory."""
    data = bytearray(archive)
    start = 0
    while (start := data.find(b"PK\x01\x02", start)) != -1:
        length = int.from_bytes(data[start + 28 : start + 30], "little")
        if data[start + 46 : start + 46 + length] == name.encode():
            data[start + 8] |= 0x1
        start += 4
    return bytes(data)


def test_an_encrypted_file_is_refused() -> None:
    archive = _marked_encrypted(
        _zip(("assets/hidden.js", b"x"), *BUILT_SITE.items()), "assets/hidden.js"
    )

    with pytest.raises(DashboardPackageError, match="encrypted"):
        read_archive(archive)


def test_a_name_given_twice_is_refused() -> None:
    with pytest.raises(DashboardPackageError, match="twice"):
        read_archive(_zip(("index.html", b"a"), ("index.html", b"b")))


def test_too_many_files_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dashboard_package, "ARCHIVE_MAX_FILES", 3)

    with pytest.raises(DashboardPackageError, match="more than 3 files"):
        read_archive(pack(BUILT_SITE))


def test_a_zip_unpacking_past_the_limit_is_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dashboard_package, "ARCHIVE_MAX_UNPACKED_BYTES", 1000)
    # Ten thousand zeros weigh a few dozen bytes once compressed.
    archive = pack({"index.html": b"0" * 10_000})

    with pytest.raises(DashboardPackageError, match="more than 1000 bytes"):
        read_archive(archive)


def test_a_damaged_zip_is_refused() -> None:
    with pytest.raises(DashboardPackageError, match="not a readable zip"):
        read_archive(b"PK\x03\x04 this is not really a zip")


# --- config.js and the zip for the host ------------------------------------------


def test_config_holds_the_two_public_values_as_data() -> None:
    script = config_script(SETTINGS).decode()

    prefix = "window.__THREADLINE_CONFIG__ = Object.freeze("
    assert script.startswith(prefix)
    assert json.loads(script.removeprefix(prefix).removesuffix(");\n")) == {
        "supabaseUrl": PROJECT_URL,
        "supabaseAnonKey": GOOD_PUBLISHABLE,
    }


@pytest.mark.parametrize("key", ['a"});alert(1);//', "a b", "key\u00e9"])
def test_config_refuses_a_key_that_is_not_plain(key: str) -> None:
    with pytest.raises(ValidationFailedError, match="letters"):
        config_script(BrowserSettings(supabase_url=PROJECT_URL, publishable_key=key))


def test_config_refuses_a_secret_key() -> None:
    with pytest.raises(ValidationFailedError, match="secret key"):
        config_script(BrowserSettings(supabase_url=PROJECT_URL, publishable_key="sb_secret_x"))


def test_config_refuses_an_address_that_is_not_a_project() -> None:
    with pytest.raises(ValidationFailedError, match="supabase.co"):
        config_script(BrowserSettings(supabase_url="https://evil.example", publishable_key="k"))


def test_the_archive_for_the_host_adds_config_and_keeps_every_file() -> None:
    archive = publishable_archive(BUILT_SITE, SETTINGS)

    files = read_archive(archive)
    assert files.pop("config.js") == config_script(SETTINGS)
    assert files == BUILT_SITE


def test_the_same_files_always_make_the_same_archive() -> None:
    assert pack(BUILT_SITE) == pack(dict(reversed(BUILT_SITE.items())))


def test_a_site_without_its_page_is_refused() -> None:
    with pytest.raises(DashboardPackageError, match="no index.html"):
        publishable_archive({"assets/a.js": b"x"}, SETTINGS)


def test_a_site_that_already_has_a_config_is_refused() -> None:
    with pytest.raises(DashboardPackageError, match="already holds a config.js"):
        publishable_archive({**BUILT_SITE, "config.js": b"window.x = 1"}, SETTINGS)


def test_a_local_build_with_an_unsafe_name_is_refused() -> None:
    with pytest.raises(DashboardPackageError, match="outside the site"):
        publishable_archive({**BUILT_SITE, "../x.js": b"x"}, SETTINGS)
