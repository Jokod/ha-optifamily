"""Installation automatique des blueprints (HACS)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from custom_components.optifamily import blueprints as bp


def test_install_blueprints_sync_copies_yaml(hass: MagicMock, tmp_path: Path) -> None:
    copied = bp.install_blueprints_sync(hass)
    assert copied >= 12
    auto = tmp_path / "blueprints" / "automation" / "optifamily"
    script = tmp_path / "blueprints" / "script" / "optifamily"
    assert (auto / "nouveau_message.yaml").is_file()
    assert (auto / "nouvelle_photo.yaml").is_file()
    assert (script / "resume_famille.yaml").is_file()


def test_install_blueprints_missing_source(
    hass: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bp, "_SOURCE", Path("/tmp/optifamily-no-blueprints"))
    assert bp.install_blueprints_sync(hass) == 0


def test_install_blueprints_skips_missing_kind(
    hass: MagicMock, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(bp, "_KINDS", ("automation", "missing-kind"))
    copied = bp.install_blueprints_sync(hass)
    assert copied >= 1
    assert not (tmp_path / "blueprints" / "missing-kind").exists()


def test_uninstall_blueprints_removes_shipped_keeps_extras(hass: MagicMock, tmp_path: Path) -> None:
    bp.install_blueprints_sync(hass)
    auto = tmp_path / "blueprints" / "automation" / "optifamily"
    extra = auto / "perso.yaml"
    extra.write_text("x", encoding="utf-8")
    removed = bp.uninstall_blueprints_sync(hass)
    assert removed >= 1
    assert not (auto / "nouveau_message.yaml").exists()
    assert extra.is_file()
    assert auto.is_dir()
    other = tmp_path / "blueprints" / "automation" / "homeassistant"
    other.mkdir(parents=True)
    (other / "notify.yaml").write_text("keep", encoding="utf-8")
    bp.uninstall_blueprints_sync(hass)
    assert (other / "notify.yaml").is_file()


def test_uninstall_blueprints_missing_dest(hass: MagicMock) -> None:
    assert bp.uninstall_blueprints_sync(hass) == 0


def test_uninstall_blueprints_without_source_still_allowlist_only(
    hass: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "blueprints" / "automation" / "optifamily"
    dest.mkdir(parents=True)
    (dest / "nouveau_message.yaml").write_text("x", encoding="utf-8")
    (dest / "perso.yaml").write_text("keep", encoding="utf-8")
    other = tmp_path / "blueprints" / "automation" / "homeassistant"
    other.mkdir(parents=True)
    (other / "notify.yaml").write_text("keep", encoding="utf-8")
    monkeypatch.setattr(bp, "_SOURCE", Path("/tmp/optifamily-no-blueprints"))
    bp.uninstall_blueprints_sync(hass)
    assert not (dest / "nouveau_message.yaml").exists()
    assert (dest / "perso.yaml").is_file()
    assert (other / "notify.yaml").is_file()


@pytest.mark.asyncio
async def test_async_install_blueprints_swallows_errors(hass: MagicMock) -> None:
    hass.config.path = MagicMock(side_effect=OSError("disk"))
    await bp.async_install_blueprints(hass)


@pytest.mark.asyncio
async def test_async_uninstall_blueprints_swallows_errors(hass: MagicMock) -> None:
    hass.config.path = MagicMock(side_effect=OSError("disk"))
    await bp.async_uninstall_blueprints(hass)


def test_shipped_allowlist_matches_files_on_disk() -> None:
    for kind, names in bp._SHIPPED.items():
        on_disk = {p.name for p in (bp._SOURCE / kind).glob("*.yaml")}
        assert on_disk == set(names)


def test_blueprints_use_phase_attrs_not_regex() -> None:
    """Plan 1.1.0 : plus de parse horaires Jinja dans les blueprints."""
    for path in (bp._SOURCE).rglob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        assert "regex_findall" not in text, path.name
        assert "sensor.optifamily_phase_journee" not in text, path.name


def test_install_skips_yaml_not_in_allowlist(
    hass: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "src" / "automation"
    src.mkdir(parents=True)
    (src / "nouveau_message.yaml").write_text("ok", encoding="utf-8")
    (src / "intrus.yaml").write_text("nope", encoding="utf-8")
    monkeypatch.setattr(bp, "_SOURCE", tmp_path / "src")
    monkeypatch.setattr(bp, "_KINDS", ("automation",))
    bp.install_blueprints_sync(hass)
    dest = tmp_path / "blueprints" / "automation" / "optifamily"
    assert (dest / "nouveau_message.yaml").is_file()
    assert not (dest / "intrus.yaml").exists()


def test_uninstall_rmdir_empty_folder(hass: MagicMock, tmp_path: Path) -> None:
    dest = tmp_path / "blueprints" / "automation" / "optifamily"
    dest.mkdir(parents=True)
    (dest / "nouveau_message.yaml").write_text("x", encoding="utf-8")
    bp.uninstall_blueprints_sync(hass)
    assert not dest.exists()


def test_uninstall_iterdir_oserror(
    hass: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "blueprints" / "automation" / "optifamily"
    dest.mkdir(parents=True)
    (dest / "nouveau_message.yaml").write_text("x", encoding="utf-8")

    real_path = Path

    class BoomPath(type(dest)):
        def iterdir(self):
            raise OSError("denied")

    def fake_path(arg):
        p = real_path(arg)
        if p.name == "optifamily" and p.parent.name == "automation":
            return BoomPath(arg)
        return p

    monkeypatch.setattr(bp, "Path", fake_path)
    assert bp.uninstall_blueprints_sync(hass) >= 0


@pytest.mark.asyncio
async def test_async_install_and_uninstall_log_success(
    hass: MagicMock, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    await bp.async_install_blueprints(hass)
    assert "installé" in caplog.text
    await bp.async_uninstall_blueprints(hass)
    assert "retiré" in caplog.text
