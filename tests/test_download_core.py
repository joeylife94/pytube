"""Unit tests for the authoritative yt-dlp download core."""

import os

import download_core


def test_build_options_captures_runtime_controls(tmp_path, monkeypatch):
    monkeypatch.setattr(download_core, "YTDLP_AVAILABLE", True)
    monkeypatch.setattr(download_core.shutil, "which", lambda name: None)

    cookiefile = tmp_path / "cookies.txt"
    cookiefile.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")

    options = download_core.build_ytdlp_options(
        str(tmp_path),
        resolution="1080p",
        subtitle_langs=["en", "ko"],
        rate_limit_kbps=512,
        cookies_from_browser="chrome",
        proxy="socks5://127.0.0.1:1080",
        cookiefile=str(cookiefile),
        filename_template="%(upload_date)s_%(title)s",
    )

    assert "height<=1080" in options["format"]
    assert options["merge_output_format"] == "mp4"
    assert options["subtitleslangs"] == ["en", "ko"]
    assert options["writesubtitles"] is True
    assert options["ratelimit"] == 512 * 1024
    assert options["cookiesfrombrowser"] == ("chrome",)
    assert options["cookiefile"] == str(cookiefile)
    assert options["proxy"] == "socks5://127.0.0.1:1080"
    assert "%(upload_date)s_%(title)s.%(ext)s" in options["outtmpl"]
    assert len(options["progress_hooks"]) == 1


def test_mp3_requires_ffmpeg(tmp_path, monkeypatch):
    monkeypatch.setattr(download_core, "YTDLP_AVAILABLE", True)
    monkeypatch.delenv("FFMPEG_LOCATION", raising=False)
    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    monkeypatch.delenv("FFMPEG_BIN", raising=False)
    monkeypatch.setattr(download_core.shutil, "which", lambda name: None)

    try:
        download_core.build_ytdlp_options(
            str(tmp_path), audio_only=True, convert_mp3=True
        )
    except RuntimeError as exc:
        assert "requires ffmpeg" in str(exc)
    else:
        raise AssertionError("Expected MP3 configuration to require ffmpeg")


def test_download_core_returns_postprocessed_mp3_path(tmp_path, monkeypatch):
    captured = {}

    class DummyYDL:
        def __init__(self, options):
            captured["options"] = options

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url, download=True):
            return {
                "title": "sample",
                "requested_downloads": [
                    {"filepath": str(tmp_path / "sample.webm")}
                ],
            }

        def prepare_filename(self, info):
            return str(tmp_path / "sample.webm")

    monkeypatch.setattr(download_core, "YTDLP_AVAILABLE", True)
    monkeypatch.setattr(download_core.yt_dlp, "YoutubeDL", DummyYDL)
    monkeypatch.setattr(
        download_core.shutil,
        "which",
        lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None,
    )

    result = download_core.download_with_ytdlp(
        "https://example.invalid/video",
        str(tmp_path),
        audio_only=True,
        convert_mp3=True,
    )

    assert result == str(tmp_path / "sample.mp3")
    assert captured["options"]["format"] == "bestaudio/best"
    assert captured["options"]["postprocessors"][0]["key"] == "FFmpegExtractAudio"


def test_subtitles_only_is_a_core_mode(tmp_path, monkeypatch):
    captured = {}

    class DummyYDL:
        def __init__(self, options):
            captured["options"] = options

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url, download=True):
            return {"title": "captions"}

    monkeypatch.setattr(download_core, "YTDLP_AVAILABLE", True)
    monkeypatch.setattr(download_core.yt_dlp, "YoutubeDL", DummyYDL)
    monkeypatch.setattr(download_core.shutil, "which", lambda name: None)

    result = download_core.download_with_ytdlp_result(
        "https://example.invalid/video",
        str(tmp_path),
        subtitles_only=True,
        subtitle_langs=["en", "ko"],
        convert_subtitles_to_srt=True,
    )

    assert result.filepath == str(tmp_path / "captions.*.srt")
    assert result.title == "captions"
    assert captured["options"]["skip_download"] is True
    assert captured["options"]["subtitleslangs"] == ["en", "ko"]
    assert captured["options"]["postprocessors"][0]["key"] == "FFmpegSubtitlesConvertor"


def test_helper_compatibility_facade_delegates(monkeypatch, tmp_path):
    import pytube_helper

    captured = {}

    def fake_core(url, output_path, **kwargs):
        captured["url"] = url
        captured["output_path"] = output_path
        captured["kwargs"] = kwargs
        return os.path.join(output_path, "delegated.mp4")

    monkeypatch.setattr(pytube_helper, "YTDLP_AVAILABLE", True)
    monkeypatch.setattr(pytube_helper, "_core_download_with_ytdlp", fake_core)

    result = pytube_helper.download_with_ytdlp(
        "https://example.invalid/video",
        str(tmp_path),
        resolution="720p",
        rate_limit_kbps=128,
        subtitle_langs=["ko"],
    )

    assert result.endswith("delegated.mp4")
    assert captured["url"] == "https://example.invalid/video"
    assert captured["kwargs"]["resolution"] == "720p"
    assert captured["kwargs"]["rate_limit_kbps"] == 128
    assert captured["kwargs"]["subtitle_langs"] == ["ko"]


def test_downloader_manager_ytdlp_runtime_delegates_to_core(tmp_path, monkeypatch):
    import downloader_manager

    captured = {}

    def fake_core(url, output_path, **kwargs):
        captured["url"] = url
        captured["output_path"] = output_path
        captured["kwargs"] = kwargs
        return download_core.DownloadResult(
            filepath=str(tmp_path / "managed.mp3"),
            title="Managed",
        )

    monkeypatch.setattr(downloader_manager, "download_with_ytdlp_result", fake_core)
    downloader = downloader_manager.YoutubeDownloader(
        output_dir=str(tmp_path),
        preferred_engine="yt-dlp",
    )

    result = downloader._download_with_ytdlp(
        "https://example.invalid/video",
        downloader_manager.DownloadMode.MP3,
    )

    assert result.success is True
    assert result.file_path == str(tmp_path / "managed.mp3")
    assert result.engine == "yt-dlp"
    assert captured["kwargs"]["audio_only"] is True
    assert captured["kwargs"]["convert_mp3"] is True
