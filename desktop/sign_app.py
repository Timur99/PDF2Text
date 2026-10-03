"""Sign the assembled app inside out, including PyInstaller code in Resources."""

import argparse
from pathlib import Path
import subprocess


# Thin and universal Mach-O headers, in both byte orders. Looking at contents
# also finds extension modules and executables without a filename extension.
MACHO_MAGICS = {
    b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
    b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca",
}
BUNDLE_SUFFIXES = {".framework", ".app", ".xpc", ".bundle"}


def signing_targets(app: Path) -> list[Path]:
    binaries = []
    bundles = []
    for path in app.rglob("*"):
        # Sign real files once; preserve the framework and library symlinks.
        if path.is_symlink():
            continue
        if path.is_dir() and path.suffix in BUNDLE_SUFFIXES:
            bundles.append(path)
        elif path.is_file():
            with path.open("rb") as source:
                if source.read(4) in MACHO_MAGICS:
                    binaries.append(path)
    # A framework's signature must include its already-signed nested code.
    return sorted(binaries) + sorted(
        bundles, key=lambda path: (-len(path.parts), str(path))
    ) + [app]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path)
    parser.add_argument("--identity", default="-")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    app = args.app.resolve()
    if not (app / "Contents/Info.plist").is_file():
        parser.error(f"Not an application bundle: {app}")
    targets = signing_targets(app)
    if not args.verify_only:
        signing_options = ["--force", "--sign", args.identity]
        if args.identity != "-":
            signing_options += ["--options", "runtime", "--timestamp"]
        for target in targets:
            subprocess.run(["codesign", *signing_options, str(target)], check=True)
    # --deep alone can miss code stored in Resources. Verify each component,
    # then the whole bundle, and fail the build on the first broken signature.
    for target in targets:
        subprocess.run(
            ["codesign", "--verify", "--strict", str(target)], check=True
        )
    subprocess.run(
        ["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)],
        check=True,
    )
    print(f"Verified {len(targets)} signed components in {app.name}", flush=True)


if __name__ == "__main__":
    main()
