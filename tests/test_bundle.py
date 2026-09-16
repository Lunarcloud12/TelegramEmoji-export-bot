import io
from dataclasses import replace
from unittest.mock import patch
from zipfile import ZipFile

import imageio_ffmpeg
from PIL import Image, ImageDraw

from emojigif.bot import run_conversion
from emojigif.bundle import create_bundle, render_frames
from emojigif.settings import ExportSettings


def inspect_video(path):
    reader = imageio_ffmpeg.read_frames(
        str(path),
        pix_fmt="rgba",
        bits_per_pixel=32,
        input_params=["-c:v", "libvpx-vp9"] if path.suffix == ".webm" else [],
    )
    try:
        metadata = next(reader)
        first = next(reader)
        last, count = first, 1
        for frame in reader:
            last = frame
            count += 1
        return (
            metadata,
            count,
            Image.frombytes("RGBA", metadata["size"], first),
            Image.frombytes("RGBA", metadata["size"], last),
        )
    finally:
        reader.close()


def test_animated_bundle_sizes_motion_alpha_and_first_frame(tgs_file, tmp_path):
    output = tmp_path / "emoji.zip"
    run_conversion(tgs_file, output)
    with ZipFile(output) as archive:
        for size in (128, 256, 512):
            with Image.open(io.BytesIO(archive.read(f"{size}/first-frame.png"))) as png:
                assert png.size == (size, size)
                assert png.getpixel((0, 0))[3] == 0
                assert png.getpixel((size // 4, size // 2)) == (255, 0, 0, 255)
            with Image.open(io.BytesIO(archive.read(f"{size}/emoji.gif"))) as gif:
                assert gif.size == (size, size)
                assert gif.n_frames > 10
                first = gif.convert("RGBA")
                duration = 0
                for index in range(gif.n_frames):
                    gif.seek(index)
                    duration += gif.info["duration"]
                assert 950 <= duration <= 1050
                assert first.getbbox()[0] < gif.convert("RGBA").getbbox()[0]
            for extension in ("mp4", "webm", "mov"):
                path = tmp_path / f"check-{size}.{extension}"
                path.write_bytes(archive.read(f"{size}/emoji.{extension}"))
                metadata, count, first, last = inspect_video(path)
                assert metadata["size"] == (size, size)
                assert metadata["fps"] == 25
                assert 24 <= count <= 26
                assert first.tobytes() != last.tobytes()
                if extension in {"webm", "mov"}:
                    assert first.getpixel((0, 0))[3] == 0
                    assert first.getbbox()[0] < last.getbbox()[0]
                else:
                    assert all(channel >= 245 for channel in first.getpixel((0, 0)))


def test_static_non_square_bundle_preserves_aspect_and_video_duration(tmp_path):
    source, output = tmp_path / "source.png", tmp_path / "emoji.zip"
    image = Image.new("RGBA", (101, 37), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((20, 10, 70, 25), fill=(0, 255, 0, 128))
    image.save(source)
    create_bundle(source, output)
    with ZipFile(output) as archive:
        for size in (128, 256, 512):
            height = round(37 * size / 101)
            with Image.open(io.BytesIO(archive.read(f"{size}/first-frame.png"))) as png:
                assert png.size == (size, height)
                assert png.getpixel((size // 2, height // 2))[3] == 128
            with Image.open(io.BytesIO(archive.read(f"{size}/emoji.gif"))) as gif:
                assert gif.size == (size, height)
                assert gif.n_frames == 1
            for extension in ("mp4", "webm", "mov"):
                path = tmp_path / f"check-{size}.{extension}"
                path.write_bytes(archive.read(f"{size}/emoji.{extension}"))
                metadata, count, first, last = inspect_video(path)
                assert metadata["size"] == (size, height + height % 2)
                assert count == 25
                if extension in {"webm", "mov"}:
                    assert first.getpixel((0, 0))[3] == 0
                    assert 120 <= first.getpixel((size // 2, height // 2))[3] <= 136


def test_animated_webp_keeps_variable_timing_and_first_frame(tmp_path):
    source = tmp_path / "animated.webp"
    frames = [Image.new("RGBA", (32, 32), color) for color in ("red", "green", "blue")]
    frames[0].save(
        source,
        save_all=True,
        append_images=frames[1:],
        duration=[40, 160, 400],
        lossless=True,
        loop=0,
    )
    rendered = render_frames(source, tmp_path / "frames")
    assert len(rendered) == 15  # 600 ms at 25 fps.
    for index, expected in [(0, (255, 0, 0)), (1, (0, 128, 0)), (5, (0, 0, 255))]:
        with Image.open(rendered[index]) as frame:
            assert frame.getpixel((256, 256))[:3] == expected


def test_only_png_does_not_encode_video_or_render_entire_animation(tgs_file, tmp_path):
    settings = ExportSettings(sizes=(96, 320), png="only", formats=())
    output = tmp_path / "only.zip"
    with patch("emojigif.bundle.ffmpeg") as encoder:
        create_bundle(tgs_file, output, settings)
        encoder.assert_not_called()
    with ZipFile(output) as archive:
        assert set(archive.namelist()) == {
            "96/first-frame.png",
            "320/first-frame.png",
        }
        with Image.open(io.BytesIO(archive.read("320/first-frame.png"))) as png:
            assert png.size == (320, 320)
            assert png.getpixel((80, 160)) == (255, 0, 0, 255)


def test_selected_mov_with_alpha_without_mp4_and_no_png(tgs_file, tmp_path):
    settings = ExportSettings(sizes=(96,), formats=("mov",), png="none", fps=50)
    output = tmp_path / "selected.zip"
    run_conversion(tgs_file, output, settings)
    with ZipFile(output) as archive:
        assert set(archive.namelist()) == {"96/emoji.mov"}
        path = tmp_path / "selected.mov"
        path.write_bytes(archive.read("96/emoji.mov"))
    metadata, count, first, last = inspect_video(path)
    assert "prores" in metadata["codec"]
    assert count == 50
    assert first.getpixel((0, 0))[3] == 0
    assert first.getbbox()[0] < last.getbbox()[0]


def test_background_quality_and_still_duration(tmp_path):
    source = tmp_path / "source.png"
    Image.new("RGBA", (64, 64), (0, 0, 0, 0)).save(source)
    output = tmp_path / "black.zip"
    settings = ExportSettings(
        sizes=(64,), formats=("mp4",), background="black", quality="small", fps=10, still_seconds=3
    )
    create_bundle(source, output, settings)
    with ZipFile(output) as archive:
        path = tmp_path / "black.mp4"
        path.write_bytes(archive.read("64/emoji.mp4"))
        with Image.open(io.BytesIO(archive.read("64/first-frame.png"))) as png:
            assert png.getpixel((0, 0)) == (0, 0, 0, 255)
    metadata, count, first, last = inspect_video(path)
    assert metadata["fps"] == 10
    assert count == 30
    assert first.getpixel((0, 0)) == (0, 0, 0, 255)
    white = replace(settings, png="only", background="white")
    create_bundle(source, tmp_path / "white.zip", white)
    with ZipFile(tmp_path / "white.zip") as archive:
        with Image.open(io.BytesIO(archive.read("64/first-frame.png"))) as png:
            assert png.getpixel((0, 0)) == (255, 255, 255, 255)
