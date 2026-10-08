"""Verify the built sdist and wheel each contain the repository license."""

from pathlib import Path
from tarfile import open as open_tar
from zipfile import ZipFile

root = Path(__file__).resolve().parents[1]
license_bytes = (root / "LICENSE").read_bytes()
dist = root / "python" / "dist"
sdists = list(dist.glob("*.tar.gz"))
wheels = list(dist.glob("*.whl"))
assert len(sdists) == len(wheels) == 1, "Expected one sdist and one wheel"

with open_tar(sdists[0]) as archive:
    files = [member for member in archive.getmembers() if member.name.endswith("/LICENSE")]
    assert len(files) == 1, "sdist must contain LICENSE"
    license_file = archive.extractfile(files[0])
    assert license_file is not None
    assert license_file.read() == license_bytes

with ZipFile(wheels[0]) as archive:
    files = [name for name in archive.namelist() if name.endswith("/LICENSE")]
    assert len(files) == 1, "wheel must contain LICENSE"
    assert archive.read(files[0]) == license_bytes

print("Both Python distributions include the repository license")
