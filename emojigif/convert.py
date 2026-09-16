"""Bounded conversion worker. Invoked in a separate process for each input."""

import argparse
import gzip
import json
import math
import os
import subprocess
from pathlib import Path

import imageio_ffmpeg
from PIL import Image
from rlottie_python import LottieAnimation

SIZE = 256
FPS = 25
MAX_SECONDS = 10
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_PIXELS = 2048 * 2048
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class ConversionError(ValueError):
    pass


def hidden_process_options() -> dict:
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def gif_frame(image: Image.Image, size: int = SIZE, colors: int = 255) -> Image.Image:
    rgba = image.convert("RGBA")
    rgba.thumbnail((size, size), Image.Resampling.LANCZOS)
    # GIF supports one transparent palette entry. Reserve it explicitly.
    result = rgba.convert("RGB").quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    mask = rgba.getchannel("A").point(lambda alpha: 255 if alpha < 128 else 0)
    result.paste(255, mask=mask)
    palette = result.getpalette() or []
    palette.extend([0] * (768 - len(palette)))
    result.putpalette(palette)
    result.info["transparency"] = 255
    return result


def save_gif(frames: list[Image.Image], durations: list[int], output: Path) -> None:
    if not frames:
        raise ConversionError("The file contains no frames.")
    frames[0].save(
        output,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        transparency=255,
        disposal=2,
        optimize=False,
    )


def validate_lottie(data: dict) -> None:
    try:
        width, height = int(data["w"]), int(data["h"])
        fps = float(data["fr"])
        first, last = float(data.get("ip", 0)), float(data["op"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ConversionError("Invalid TGS file.") from exc
    if not all(math.isfinite(n) for n in (fps, first, last)):
        raise ConversionError("Invalid TGS duration.")
    if not (0 < width <= 2048 and 0 < height <= 2048 and 0 < fps <= 120):
        raise ConversionError("Unsupported TGS dimensions or frame rate.")
    if not (0 <= first < last and (last - first) / fps <= MAX_SECONDS):
        raise ConversionError("The animation must be no longer than 10 seconds.")

    # Emoji TGS uses vectors. Reject embedded/external images and text resources.
    def check(node: object) -> None:
        if isinstance(node, dict):
            if ("p" in node and "u" in node) or node.get("ty") in (2, 5):
                raise ConversionError("TGS files with external resources are not supported.")
            for value in node.values():
                check(value)
        elif isinstance(node, list):
            for value in node:
                check(value)

    check(data)


def read_lottie(source: Path) -> dict:
    with gzip.open(source, "rb") as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise ConversionError("The decompressed TGS file is too large.")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ConversionError("Invalid TGS file.")
    validate_lottie(data)
    return data


def tgs_to_gif(source: Path, output: Path) -> None:
    data = read_lottie(source)
    with LottieAnimation.from_data(json.dumps(data)) as animation:
        source_fps = animation.lottie_animation_get_framerate()
        total = animation.lottie_animation_get_totalframe()
        if total <= 0 or source_fps <= 0:
            raise ConversionError("The TGS file contains no animation.")
        duration = (data["op"] - data.get("ip", 0)) / data["fr"]
        if duration > MAX_SECONDS + 0.1:
            raise ConversionError("The animation is too long.")
        width, height = animation.lottie_animation_get_size()
        scale = SIZE / max(width, height)
        width, height = max(1, round(width * scale)), max(1, round(height * scale))
        count = max(1, math.ceil(duration * FPS))
        frames = [
            gif_frame(
                animation.render_pillow_frame(
                    frame_num=min(total - 1, int(index * source_fps / FPS)),
                    width=width,
                    height=height,
                )
            )
            for index in range(count)
        ]
        save_gif(frames, [40] * count, output)


def image_to_gif(source: Path, output: Path) -> None:
    with Image.open(source) as image:
        if image.width * image.height > MAX_PIXELS:
            raise ConversionError("The image dimensions are too large.")
        count = getattr(image, "n_frames", 1)
        if count > MAX_SECONDS * 60:
            raise ConversionError("The file contains too many frames.")
        frames, durations = [], []
        elapsed = 0
        for index in range(count):
            image.seek(index)
            image.load()
            delay = max(20, int(image.info.get("duration", 100)))
            elapsed += delay
            if elapsed > MAX_SECONDS * 1000:
                raise ConversionError("The animation must be no longer than 10 seconds.")
            frames.append(gif_frame(image))
            durations.append(delay)
        save_gif(frames, durations, output)


def webm_to_gif(source: Path, output: Path) -> None:
    # Telegram video stickers use VP9. libvpx-vp9 preserves its alpha channel.
    filters = (
        f"fps={FPS},scale={SIZE}:{SIZE}:force_original_aspect_ratio=decrease:"
        "flags=lanczos,split[a][b];"
        "[a]palettegen=reserve_transparent=1:stats_mode=diff[p];"
        "[b][p]paletteuse=alpha_threshold=128:dither=sierra2_4a"
    )
    command = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-protocol_whitelist",
        "file,pipe",
        "-threads",
        "2",
        "-c:v",
        "libvpx-vp9",
        "-i",
        str(source),
        "-t",
        str(MAX_SECONDS),
        "-filter_complex_threads",
        "1",
        "-filter_complex",
        filters,
        "-an",
        "-loop",
        "0",
        str(output),
    ]
    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=40,
            **hidden_process_options(),
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ConversionError("Could not read WEBM. Please send a VP9 video sticker.") from exc


def convert(source: Path, output: Path) -> None:
    if source.stat().st_size > MAX_FILE_BYTES:
        raise ConversionError("The file exceeds 10 MB.")
    suffix = source.suffix.lower()
    if suffix == ".tgs":
        tgs_to_gif(source, output)
    elif suffix == ".webm":
        webm_to_gif(source, output)
    elif suffix in {".png", ".webp"}:
        image_to_gif(source, output)
    else:
        raise ConversionError("Supported file types: TGS, WEBM, WEBP, and PNG.")
    if not output.exists() or not 0 < output.stat().st_size <= MAX_FILE_BYTES:
        raise ConversionError("The resulting GIF is empty or too large.")
    with Image.open(output) as result:
        if result.format != "GIF":
            raise ConversionError("Could not create the GIF.")
        result.verify()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--settings", type=Path)
    args = parser.parse_args()
    try:
        if args.output.suffix.lower() == ".zip":
            from emojigif.bundle import create_bundle
            from emojigif.settings import ExportSettings

            settings = (
                ExportSettings.from_json(args.settings.read_text(encoding="utf-8"))
                if args.settings
                else ExportSettings()
            )
            create_bundle(args.source, args.output, settings)
        else:
            convert(args.source, args.output)
    except Exception as exc:
        # This process never receives the bot token in its environment.
        print(str(exc) if isinstance(exc, ConversionError) else "Invalid file.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
