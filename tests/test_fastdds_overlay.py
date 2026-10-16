from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from marsdog_vision_interaction import fastdds_overlay
from marsdog_vision_interaction.fastdds_overlay import fastdds_overlay_environment

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def make_overlay(root: Path) -> Path:
    library_directory = root / "lib"
    library_directory.mkdir(parents=True)
    (library_directory / "libfastrtps.so.2.6.12").touch()
    (library_directory / "libfastrtps.so.2.6").symlink_to("libfastrtps.so.2.6.12")
    return library_directory


def test_overlay_precedes_existing_libraries_without_dropping_them(tmp_path: Path) -> None:
    library_directory = make_overlay(tmp_path / "fastdds")
    updates = fastdds_overlay_environment({
        "MARSDOG_FASTDDS_PREFIX": str(library_directory.parent),
        "LD_LIBRARY_PATH": f"/opt/ros/humble/lib:{library_directory}:/usr/local/lib",
    })

    assert updates == {
        "LD_LIBRARY_PATH": f"{library_directory}:/opt/ros/humble/lib:/usr/local/lib"
    }


def test_explicit_missing_overlay_fails_instead_of_silently_using_system_library(
    tmp_path: Path,
) -> None:
    with pytest.raises(FileNotFoundError, match="does not contain Fast DDS 2.6.12"):
        fastdds_overlay_environment({
            "MARSDOG_FASTDDS_PREFIX": str(tmp_path / "missing"),
        })


def test_absent_default_overlay_preserves_existing_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fastdds_overlay, "DEFAULT_PREFIX", tmp_path / "missing")

    assert fastdds_overlay_environment({"LD_LIBRARY_PATH": "/opt/ros/humble/lib"}) == {}


def test_present_but_incomplete_default_overlay_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prefix = tmp_path / "incomplete"
    prefix.mkdir()
    monkeypatch.setattr(fastdds_overlay, "DEFAULT_PREFIX", prefix)

    with pytest.raises(FileNotFoundError, match="libfastrtps.so.2.6 is missing"):
        fastdds_overlay_environment({})


def test_versioned_library_without_runtime_soname_is_rejected(tmp_path: Path) -> None:
    library_directory = tmp_path / "fastdds" / "lib"
    library_directory.mkdir(parents=True)
    (library_directory / "libfastrtps.so.2.6.12").touch()

    with pytest.raises(FileNotFoundError, match="does not contain Fast DDS 2.6.12"):
        fastdds_overlay_environment({
            "MARSDOG_FASTDDS_PREFIX": str(library_directory.parent),
        })


def test_dangling_soname_link_is_rejected(tmp_path: Path) -> None:
    library_directory = tmp_path / "fastdds" / "lib"
    library_directory.mkdir(parents=True)
    (library_directory / "libfastrtps.so.2.6").symlink_to("missing-runtime.so")

    with pytest.raises(FileNotFoundError, match="does not contain Fast DDS 2.6.12"):
        fastdds_overlay_environment({
            "MARSDOG_FASTDDS_PREFIX": str(library_directory.parent),
        })


def test_disable_overlay_removes_its_library_directory(tmp_path: Path) -> None:
    library_directory = make_overlay(tmp_path / "fastdds")
    updates = fastdds_overlay_environment({
        "MARSDOG_FASTDDS_PREFIX": str(library_directory.parent),
        "MARSDOG_FASTDDS_DISABLE_OVERLAY": "1",
        "LD_LIBRARY_PATH": f"{library_directory}:/opt/ros/humble/lib",
    })

    assert updates == {"LD_LIBRARY_PATH": "/opt/ros/humble/lib"}


def test_source_script_exports_the_same_overlay_and_ros_settings(tmp_path: Path) -> None:
    library_directory = make_overlay(tmp_path / "fastdds")
    environment = os.environ.copy()
    environment.update({
        "MARSDOG_FASTDDS_PREFIX": str(library_directory.parent),
        "LD_LIBRARY_PATH": f"/opt/ros/humble/lib:{library_directory}",
    })
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                'source "$1"; printf "%s\\n%s\\n%s\\n" "$LD_LIBRARY_PATH" '
                '"$RMW_IMPLEMENTATION" "$RMW_FASTRTPS_USE_QOS_FROM_XML"'
            ),
            "bash",
            str(PROJECT_ROOT / "scripts" / "fastdds_env.sh"),
        ],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.splitlines() == [
        f"{library_directory}:/opt/ros/humble/lib",
        "rmw_fastrtps_cpp",
        "0",
    ]


def test_installed_share_script_uses_adjacent_helper_from_external_directory(
    tmp_path: Path,
) -> None:
    library_directory = make_overlay(tmp_path / "fastdds")
    share = tmp_path / "install" / "share" / "marsdog_vision_interaction"
    (share / "config").mkdir(parents=True)
    shutil.copyfile(PROJECT_ROOT / "scripts" / "fastdds_env.sh", share / "fastdds_env.sh")
    shutil.copyfile(
        PROJECT_ROOT / "marsdog_vision_interaction" / "fastdds_overlay.py",
        share / "fastdds_overlay.py",
    )
    shutil.copyfile(PROJECT_ROOT / "config" / "fastdds.xml", share / "config" / "fastdds.xml")
    environment = os.environ.copy()
    environment.update({
        "MARSDOG_FASTDDS_PREFIX": str(library_directory.parent),
        "LD_LIBRARY_PATH": "/opt/ros/humble/lib",
    })
    environment.pop("PYTHONPATH", None)
    environment.pop("MARSDOG_FASTDDS_PROFILE", None)
    result = subprocess.run(
        [
            "bash", "-c",
            (
                'source "$1" || exit; printf "%s\\n%s\\n" '
                '"$LD_LIBRARY_PATH" "$FASTRTPS_DEFAULT_PROFILES_FILE"'
            ),
            "bash", str(share / "fastdds_env.sh"),
        ],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.splitlines() == [
        f"{library_directory}:/opt/ros/humble/lib",
        str(share / "config" / "fastdds.xml"),
    ]


@pytest.mark.parametrize("launch_name", ["vision.launch.py", "vision_debug.launch.py"])
def test_launch_applies_the_shared_fastdds_overlay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    launch_name: str,
) -> None:
    launch = pytest.importorskip("launch")
    library_directory = make_overlay(tmp_path / "fastdds")
    monkeypatch.setenv("MARSDOG_FASTDDS_PREFIX", str(library_directory.parent))
    monkeypatch.setenv("LD_LIBRARY_PATH", "/opt/ros/humble/lib")

    launch_path = PROJECT_ROOT / "launch" / launch_name
    spec = importlib.util.spec_from_file_location("marsdog_test_launch", launch_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    description = module.generate_launch_description()

    context = launch.LaunchContext()
    overlay_action = next(
        action
        for action in description.entities
        if action.__class__.__name__ == "SetEnvironmentVariable"
        and action._SetEnvironmentVariable__name[0].perform(context) == "LD_LIBRARY_PATH"
    )
    overlay_action.execute(context)

    assert context.environment["LD_LIBRARY_PATH"] == (
        f"{library_directory}:/opt/ros/humble/lib"
    )
