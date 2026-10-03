"""Exercise the packaging regression with real macOS code signatures."""

from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

import pytest


pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("codesign") is None,
    reason="Requires macOS codesign",
)
SIGN_APP = Path(__file__).resolve().parents[1] / "desktop/sign_app.py"


def test_signs_app_and_nested_framework_and_rejects_tampering(tmp_path):
    binary = tmp_path / "standalone"
    shutil.copy("/usr/bin/true", binary)
    subprocess.run(["codesign", "--force", "--sign", "-", str(binary)], check=True)
    app = tmp_path / "Test App.app"
    macos = app / "Contents/MacOS"
    macos.mkdir(parents=True)
    shutil.copy(binary, macos / "TestApp")
    with (app / "Contents/Info.plist").open("wb") as target:
        plistlib.dump({
            "CFBundleExecutable": "TestApp",
            "CFBundleIdentifier": "com.pdf2text.signing-test",
            "CFBundlePackageType": "APPL",
        }, target)

    framework = app / "Contents/Resources/Test.framework"
    version = framework / "Versions/A"
    (version / "Resources").mkdir(parents=True)
    shutil.copy(binary, version / "Test")
    info = version / "Resources/Info.plist"
    with info.open("wb") as target:
        plistlib.dump({
            "CFBundleExecutable": "Test",
            "CFBundleIdentifier": "com.pdf2text.signing-test.framework",
            "CFBundlePackageType": "FMWK",
            "CFBundleVersion": "1",
        }, target)
    (framework / "Versions/Current").symlink_to("A")
    (framework / "Test").symlink_to("Versions/Current/Test")
    (framework / "Resources").symlink_to("Versions/Current/Resources")

    # Signed executables alone do not seal the app or framework resources.
    for bundle in (app, framework):
        assert subprocess.run(
            ["codesign", "--verify", "--strict", str(bundle)], capture_output=True
        ).returncode != 0

    command = [sys.executable, str(SIGN_APP), str(app)]
    subprocess.run(command, check=True)
    subprocess.run(command + ["--verify-only"], check=True)
    assert (framework / "Test").is_symlink()

    # Post-signing changes to nested resources must fail verification.
    with info.open("ab") as target:
        target.write(b"\n")
    assert subprocess.run(command + ["--verify-only"], capture_output=True).returncode != 0
