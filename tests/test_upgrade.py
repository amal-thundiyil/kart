import json
import subprocess
from pathlib import Path

import pytest

from kart.cli import get_version
from kart.exceptions import UNSUPPORTED_VERSION
from kart.repo import KartRepo


H = pytest.helpers.helpers()

POINTS_UPGRADE_RESULT = [
    f"commit {H.POINTS.HEAD_SHA}",
    "Author: Robert Coup <robert@coup.net.nz>",
    f"Date:   {H.POINTS.DATE_TIME}",
    "",
    "    Improve naming on Coromandel East coast",
    "",
    f"commit {H.POINTS.HEAD1_SHA}",
    "Author: Robert Coup <robert@coup.net.nz>",
    f"Date:   {H.POINTS.DATE_TIME1}",
    "",
    "    Import from nz-pa-points-topo-150k.gpkg",
]


@pytest.mark.slow
@pytest.mark.parametrize(
    "archive,layer",
    [
        pytest.param("points0.snow.tgz", H.POINTS.LAYER, id="points"),
        pytest.param("polygons0.snow.tgz", H.POLYGONS.LAYER, id="polygons"),
        pytest.param("table0.snow.tgz", H.TABLE.LAYER, id="table"),
    ],
)
def test_upgrade_v0(archive, layer, data_archive_readonly, cli_runner, tmp_path, chdir):
    archive_path = Path("upgrade") / "v0" / archive
    with data_archive_readonly(archive_path) as source_path:
        r = cli_runner.invoke(["data", "version", "--output-format=json"])
        assert r.exit_code == 0, r.stderr
        assert json.loads(r.stdout) == {
            "repostructure.version": 0,
            "localconfig.branding": "sno",
        }

        r = cli_runner.invoke(["log"])
        assert r.exit_code == UNSUPPORTED_VERSION
        assert "This Kart repo uses Datasets v0" in r.stderr
        assert f"Kart {get_version()} only supports Datasets v2" in r.stderr

        r = cli_runner.invoke(["upgrade", source_path, tmp_path / "dest"])
        assert r.exit_code == 0, r.stderr
        assert r.stdout.splitlines()[-1] == "Upgrade complete"

    with chdir(tmp_path / "dest"):
        r = cli_runner.invoke(["log"])
        assert r.exit_code == 0, r.stderr

        if layer == H.POINTS.LAYER:
            assert r.stdout.splitlines()[:2] == POINTS_UPGRADE_RESULT[:2]
            assert r.stdout.splitlines()[3:8] == POINTS_UPGRADE_RESULT[3:8]
            assert r.stdout.splitlines()[9:] == POINTS_UPGRADE_RESULT[9:]


@pytest.mark.slow
@pytest.mark.parametrize(
    "archive,layer",
    [
        pytest.param("points.tgz", H.POINTS.LAYER, id="points"),
        pytest.param("polygons.tgz", H.POLYGONS.LAYER, id="polygons"),
        pytest.param("table.tgz", H.TABLE.LAYER, id="table"),
    ],
)
def test_upgrade_v1(archive, layer, data_archive_readonly, cli_runner, tmp_path, chdir):
    archive_path = Path("upgrade") / "v1" / archive
    with data_archive_readonly(archive_path) as source_path:
        r = cli_runner.invoke(["data", "version", "--output-format=json"])
        assert r.exit_code == 0, r.stderr
        assert json.loads(r.stdout) == {
            "repostructure.version": 1,
            "localconfig.branding": "sno",
        }

        r = cli_runner.invoke(["log"])
        assert r.exit_code == UNSUPPORTED_VERSION
        assert "This Kart repo uses Datasets v1" in r.stderr
        assert f"Kart {get_version()} only supports Datasets v2" in r.stderr

        r = cli_runner.invoke(["upgrade", source_path, tmp_path / "dest"])
        assert r.exit_code == 0, r.stderr
        assert r.stdout.splitlines()[-1] == "Upgrade complete"

    with chdir(tmp_path / "dest"):
        r = cli_runner.invoke(["log"])
        assert r.exit_code == 0, r.stderr

        if layer == H.POINTS.LAYER:
            assert r.stdout.splitlines()[:2] == POINTS_UPGRADE_RESULT[:2]
            assert r.stdout.splitlines()[3:8] == POINTS_UPGRADE_RESULT[3:8]
            assert r.stdout.splitlines()[9:] == POINTS_UPGRADE_RESULT[9:]

        r = cli_runner.invoke(["status", "--output-format=json"])
        assert r.exit_code == 0, r


@pytest.mark.slow
@pytest.mark.parametrize(
    "archive,layer",
    [
        pytest.param("points.tgz", H.POINTS.LAYER, id="points"),
        pytest.param("polygons.tgz", H.POLYGONS.LAYER, id="polygons"),
        pytest.param("table.tgz", H.TABLE.LAYER, id="table"),
    ],
)
@pytest.mark.parametrize(
    "branding",
    [
        pytest.param("sno"),
        pytest.param("kart"),
    ],
)
def test_upgrade_v2(
    branding, archive, layer, data_archive_readonly, cli_runner, tmp_path, chdir
):
    archive_path = Path("upgrade") / f"v2.{branding}" / archive
    with data_archive_readonly(archive_path) as source_path:
        r = cli_runner.invoke(["data", "version", "--output-format=json"])
        assert r.exit_code == 0, r.stderr
        assert json.loads(r.stdout) == {
            "repostructure.version": 2,
            "localconfig.branding": branding,
        }

        r = cli_runner.invoke(["log"])
        assert r.exit_code == 0  # V2 is still supported

        r = cli_runner.invoke(["upgrade", source_path, tmp_path / "dest"])
        assert r.exit_code == 0, r.stderr
        assert r.stdout.splitlines()[-1] == "Upgrade complete"

    with chdir(tmp_path / "dest"):
        r = cli_runner.invoke(["log"])
        assert r.exit_code == 0, r.stderr

        if layer == H.POINTS.LAYER:
            assert r.stdout.splitlines()[:2] == POINTS_UPGRADE_RESULT[:2]
            assert r.stdout.splitlines()[3:8] == POINTS_UPGRADE_RESULT[3:8]
            assert r.stdout.splitlines()[9:] == POINTS_UPGRADE_RESULT[9:]

        r = cli_runner.invoke(["status", "--output-format=json"])
        assert r.exit_code == 0, r


@pytest.mark.slow
@pytest.mark.parametrize(
    "archive,layer",
    [
        pytest.param("points.tgz", H.POINTS.LAYER, id="points"),
        pytest.param("polygons.tgz", H.POLYGONS.LAYER, id="polygons"),
        pytest.param("table.tgz", H.TABLE.LAYER, id="table"),
    ],
)
def test_upgrade_v2_in_place(archive, layer, data_archive, cli_runner, tmp_path, chdir):
    archive_path = Path("upgrade") / "v2.kart" / archive
    with data_archive(archive_path) as source_path:
        r = cli_runner.invoke(["data", "version", "--output-format=json"])
        assert r.exit_code == 0, r.stderr
        assert json.loads(r.stdout) == {
            "repostructure.version": 2,
            "localconfig.branding": "kart",
        }

        r = cli_runner.invoke(["log"])
        assert r.exit_code == 0  # V2 is still supported

        r = cli_runner.invoke(["upgrade", "--in-place", source_path, source_path])
        assert r.exit_code == 0, r.stderr
        assert r.stdout.splitlines()[-1] == "Upgrade complete"

        r = cli_runner.invoke(["data", "version", "--output-format=json"])
        assert r.exit_code == 0, r.stderr
        assert json.loads(r.stdout) == {
            "repostructure.version": 3,
            "localconfig.branding": "kart",
        }

        r = cli_runner.invoke(["log"])
        assert r.exit_code == 0, r.stderr

        if layer == H.POINTS.LAYER:
            assert r.stdout.splitlines()[:2] == POINTS_UPGRADE_RESULT[:2]
            assert r.stdout.splitlines()[3:8] == POINTS_UPGRADE_RESULT[3:8]
            assert r.stdout.splitlines()[9:] == POINTS_UPGRADE_RESULT[9:]


def test_upgrade_preserves_refs(data_archive, cli_runner, tmp_path):
    with data_archive("upgrade/v2.kart/points") as source_path:
        # first make a new branch, and remove 'main'
        subprocess.check_call(["git", "branch", "-m", "main", "newbranch"])

        # upgrade it
        dest = tmp_path / "dest"
        r = cli_runner.invoke(["upgrade", source_path, dest])
        assert r.exit_code == 0, r.stderr
        assert r.stdout.splitlines()[-1] == "Upgrade complete"

        # check that the refs are the same as before
        repo = KartRepo(dest)
        assert set(repo.references) == {"refs/heads/newbranch"}
