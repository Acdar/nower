"""Update source repositories are configurable and stay offline in tests."""

from unittest.mock import Mock, patch

import pytest

from arknights_mower.tests.software_update_tests import release
from arknights_mower.utils import software_update as update


@pytest.fixture
def settings(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(update, "settings_path", lambda: path)
    monkeypatch.setattr(update.runtime, "state_dir", lambda: tmp_path / "state")
    return path


@pytest.fixture
def network(monkeypatch):
    monkeypatch.setattr(update.network_settings, "apply_http_proxy", lambda: None)
    monkeypatch.setattr(
        update.network_settings,
        "get_effective_settings",
        lambda: {"http_proxy": ""},
    )


def github_response(payload):
    response = Mock(status_code=200)
    response.json.return_value = payload
    return response


def test_built_in_repositories_remain_the_default_target(settings):
    assert not settings.exists()
    assert update.get_settings()["update_repo"] == "ArkMowers/arknights-mower"
    assert update.get_settings()["ota_repo"] == "ArkMowers/MowerRelease"
    assert update.releases_url() == f"https://github.com/{update.REPO}/releases"
    assert update.ota_releases_url() == f"https://github.com/{update.OTA_REPO}/releases"
    assert (
        update.ota_index_url()
        == f"https://raw.githubusercontent.com/{update.OTA_REPO}/main/version"
    )
    assert update.update_repo() == update.REPO
    assert update.ota_repo() == update.OTA_REPO


def test_saved_repositories_replace_every_target_url(settings):
    update.save_settings(
        {
            "update_repo": "https://github.com/personal/mower.git",
            "ota_repo": "personal/releases",
        }
    )
    assert update.get_settings()["update_repo"] == "personal/mower"
    assert update.get_settings()["ota_repo"] == "personal/releases"
    assert update.releases_url() == "https://github.com/personal/mower/releases"
    assert (
        update.ota_index_url()
        == "https://raw.githubusercontent.com/personal/releases/main/version"
    )
    with patch.object(update.requests, "get", return_value=github_response({})) as get:
        update.github("/releases/latest")
    assert (
        get.call_args.args[0]
        == "https://api.github.com/repos/personal/mower/releases/latest"
    )


@pytest.mark.parametrize(
    "value",
    ["", "   ", "https://gitlab.com/personal/mower", "owner", None, 12],
)
def test_repository_answers_outside_github_are_rejected(settings, value):
    with pytest.raises(ValueError):
        update.save_settings({"ota_repo": value})
    assert update.get_settings()["ota_repo"] == "ArkMowers/MowerRelease"


def test_repository_change_invalidates_the_coalesced_automatic_check(settings):
    before = update.automatic_check_key(update.get_settings())
    update.save_settings({"update_repo": "personal/mower"})
    assert update.automatic_check_key(update.get_settings()) != before


def test_channel_index_is_read_from_the_selected_ota_repository(settings):
    update.save_settings({"ota_repo": "personal/releases"})
    index = {
        "schema": 1,
        "version": "v4.1.6",
        "full_assets": [],
        "ota_assets": [],
        "history": [],
    }
    response = Mock()
    response.json.return_value = index
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    download = Mock(return_value=(response, None))
    with patch.object(update.github_download, "request_download", download):
        assert update.release_index("stable") == index
    assert (
        download.call_args.args[2]
        == "https://raw.githubusercontent.com/personal/releases/main/version/stable.json"
    )


def test_release_asset_must_come_from_the_selected_repository(settings):
    update.save_settings({"ota_repo": "personal/releases"})
    name = "arknights-mower_4.1.6_windows_x64.zip"
    asset = {
        "name": name,
        "size": 12,
        "digest": "sha256:" + "a" * 64,
        "url": f"https://github.com/personal/releases/releases/download/v4.1.6/{name}",
    }
    with patch.object(update, "platform_asset", return_value=("windows", "x64")):
        selected = update.choose_asset(
            {"version": "v4.1.6", "full_assets": [asset]}, repo=update.ota_repo()
        )
        assert selected["url"] == asset["url"]
        with pytest.raises(ValueError, match="所选仓库"):
            update.choose_asset(
                {
                    "version": "v4.1.6",
                    "full_assets": [
                        {
                            **asset,
                            "url": asset["url"].replace(
                                "personal/releases", update.REPO
                            ),
                        }
                    ],
                },
                repo=update.ota_repo(),
            )


def test_source_tags_follow_the_selected_update_repository(settings, network):
    update.save_settings({"channel": "stable", "update_repo": "personal/mower"})
    calls = []

    def github(path, proxy="", *, repo=None):
        calls.append((path, repo))
        return (
            release("v4.1.6", system="windows", arch="x64")
            if path.endswith("latest")
            else {"sha": "a" * 40}
        )

    with (
        patch.object(update, "github", side_effect=github),
        patch.object(update.runtime, "frozen", return_value=False),
        patch.object(update.subprocess, "check_output", return_value="b" * 40),
    ):
        checked = update.check("stable", proxy="")

    plan = update._checks[checked["check_id"]]
    assert plan["source_repo"] == "personal/mower"
    assert plan["source_url"] == "https://github.com/personal/mower.git"
    assert calls[0] == ("/releases/latest", "personal/mower")
    assert calls[1] == ("/commits/v4.1.6", "personal/mower")
