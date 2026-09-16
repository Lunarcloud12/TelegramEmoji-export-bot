import gzip
import io
import json
import subprocess
from zipfile import ZipFile

import imageio_ffmpeg
import pytest
from PIL import Image, ImageDraw

from emojigif.bot import run_conversion
from emojigif.convert import ConversionError, convert, hidden_process_options


@pytest.mark.parametrize("suffix", ["png", "webp"])
def test_static_transparency(tmp_path, suffix):
    source, output = tmp_path / f"source.{suffix}", tmp_path / "result.gif"
    original = Image.new("RGBA", (72, 72), (0, 0, 0, 0))
    ImageDraw.Draw(original).ellipse((12, 12, 60, 60), fill=(255, 0, 0, 255))
    original.save(source)
    convert(source, output)
    with Image.open(output) as result:
        assert result.format == "GIF"
        assert result.n_frames == 1
        assert result.size == (72, 72)
        rgba = result.convert("RGBA")
        assert rgba.getpixel((0, 0))[3] == 0
        assert rgba.getpixel((36, 36))[0] > 240
        assert rgba.getpixel((36, 36))[3] == 255


def test_tgs_real_worker_motion_and_duration(tgs_file, tmp_path):
    output = tmp_path / "result.gif"
    run_conversion(tgs_file, output)
    with Image.open(output) as result:
        assert result.format == "GIF"
        assert result.n_frames > 10
        assert result.size == (256, 256)
        first = result.convert("RGBA")
        assert first.getpixel((0, 0))[3] == 0
        durations = []
        for index in range(result.n_frames):
            result.seek(index)
            durations.append(result.info["duration"])
        last = result.convert("RGBA")
        assert first.getbbox()[0] < last.getbbox()[0]
        assert 950 <= sum(durations) <= 1050
        assert result.info["loop"] == 0


def test_webm_real_conversion(tmp_path):
    # Encode a moving opaque square on transparent frames using actual VP9.
    for index in range(10):
        frame = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        x = 4 + 3 * index
        ImageDraw.Draw(frame).rectangle((x, 20, x + 14, 34), fill=(255, 0, 0, 255))
        frame.save(tmp_path / f"frame-{index:02}.png")
    source, output = tmp_path / "source.webm", tmp_path / "result.gif"
    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-framerate",
            "10",
            "-i",
            str(tmp_path / "frame-%02d.png"),
            "-c:v",
            "libvpx-vp9",
            "-pix_fmt",
            "yuva420p",
            "-auto-alt-ref",
            "0",
            str(source),
        ],
        check=True,
        timeout=20,
        **hidden_process_options(),
    )
    run_conversion(source, output)
    with Image.open(output) as result:
        assert result.format == "GIF"
        assert result.n_frames >= 10
        first = result.convert("RGBA")
        result.seek(result.n_frames - 1)
        last = result.convert("RGBA")
        assert first.getpixel((0, 0))[3] == 0
        assert first.getbbox()[0] < last.getbbox()[0]

    archive_path = tmp_path / "media.zip"
    run_conversion(source, archive_path)
    with ZipFile(archive_path) as archive:
        with Image.open(io.BytesIO(archive.read("512/first-frame.png"))) as png:
            assert png.size == (512, 512)
            assert png.getpixel((0, 0))[3] == 0
            assert png.getpixel((80, 200))[0] > 230
        with Image.open(io.BytesIO(archive.read("128/emoji.gif"))) as gif:
            first = gif.convert("RGBA")
            gif.seek(gif.n_frames - 1)
            assert first.getbbox()[0] < gif.convert("RGBA").getbbox()[0]


def test_invalid_file_is_reported(tmp_path):
    source, output = tmp_path / "bad.tgs", tmp_path / "result.gif"
    source.write_bytes(b"not a tgs")
    with pytest.raises(ConversionError, match="Invalid"):
        run_conversion(source, output)


def test_external_lottie_resource_rejected(tgs_file, tmp_path):
    data = json.loads(gzip.decompress(tgs_file.read_bytes()))
    data["assets"] = [{"id": "img", "p": "private.png", "u": "file:///"}]
    tgs_file.write_bytes(gzip.compress(json.dumps(data).encode()))
    with pytest.raises(ConversionError, match="resources"):
        convert(tgs_file, tmp_path / "result.gif")


def test_oversized_gzip_rejected(tmp_path):
    source = tmp_path / "huge.tgs"
    source.write_bytes(gzip.compress(b" " * (2 * 1024 * 1024 + 1)))
    with pytest.raises(ConversionError, match="decompressed"):
        convert(source, tmp_path / "result.gif")
