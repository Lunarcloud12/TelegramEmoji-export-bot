"""Offline installation check, suitable for launchers and Docker CI."""

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import imageio_ffmpeg
from PIL import Image

from emojigif.bundle import create_bundle
from emojigif.convert import hidden_process_options
from emojigif.settings import ExportSettings


def main() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "sample.png"
        image = Image.new("RGBA", (32, 32), (255, 0, 0, 0))
        image.putpixel((16, 16), (255, 0, 0, 128))
        image.save(source)
        create_bundle(source, root / "sample.zip", ExportSettings(sizes=(32,)))
        with ZipFile(root / "sample.zip") as archive:
            mov = root / "sample.mov"
            mov.write_bytes(archive.read("32/emoji.mov"))
        decoded = subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(),
                "-v",
                "error",
                "-i",
                str(mov),
                "-frames:v",
                "1",
                "-pix_fmt",
                "rgba",
                "-f",
                "rawvideo",
                "pipe:1",
            ],
            check=True,
            capture_output=True,
            **hidden_process_options(),
        )
        first = Image.frombytes("RGBA", (32, 32), decoded.stdout)
        assert first.getpixel((0, 0))[3] == 0
    print("Installation OK: GIF, MP4, WebM, MOV/ProRes alpha and PNG.")


if __name__ == "__main__":
    main()
