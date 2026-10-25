"""Unit tests for the authoritative yt-dlp download core."""

import http.server
import os
import threading

import pytest

import download_core


def test_build_options_leaves_client_selection_to_ytdlp(tmp_path, monkeypatch):
    """Forced android/ios clients, a stale UA and disabled TLS checks must not come back."""
    monkeypatch.setattr(download_core, "YTDLP_AVAILABLE", True)
    monkeypatch.setattr(download_core.shutil, "which", lambda name: None)

    options = download_core.build_ytdlp_options(str(tmp_path))

    assert "extractor_args" not in options
    assert "http_headers" not in options
    assert "nocheckcertificate" not in options


def test_js_runtime_uses_local_ejs_when_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(download_core, "YTDLP_AVAILABLE", True)
    monkeypatch.setattr(
        download_core.shutil,
        "which",
        lambda name: "/usr/bin/node" if name == "node" else None,
    )

    monkeypatch.setattr(download_core, "YTDLP_EJS_AVAILABLE", True)
    options = download_core.build_ytdlp_options(str(tmp_path))
    assert options["js_runtimes"] == {"node": {}}
    assert "remote_components" not in options

    monkeypatch.setattr(download_core, "YTDLP_EJS_AVAILABLE", False)
    options = download_core.build_ytdlp_options(str(tmp_path))
    assert options["remote_components"] == ["ejs:github"]


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
    assert options["format_sort"] == ["res", "ext:mp4:m4a"]
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

        def add_post_processor(self, pp, when="post_process"):
            pass

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

        def add_post_processor(self, pp, when="post_process"):
            pass

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


def test_download_never_clobbers_existing_files(tmp_path, monkeypatch):
    """Regression: an audio download named like an earlier video used to delete the video."""
    video = tmp_path / "Clip.webm"
    video.write_bytes(b"the earlier video")

    class DummyYDL:
        def __init__(self, options):
            self.outtmpl = options["outtmpl"]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def add_post_processor(self, pp, when="post_process"):
            pass

        def extract_info(self, url, download=True):
            # yt-dlp writes into the template's folder (the private staging dir)
            target = self.outtmpl.replace("%(title)s", "Clip").replace("%(ext)s", "webm")
            assert os.path.dirname(target) != str(tmp_path), "must not write into output folder"
            with open(target, "wb") as f:
                f.write(b"new audio")
            return {"title": "Clip", "requested_downloads": [{"filepath": target}]}

    monkeypatch.setattr(download_core, "YTDLP_AVAILABLE", True)
    monkeypatch.setattr(download_core.yt_dlp, "YoutubeDL", DummyYDL)
    monkeypatch.setattr(download_core.shutil, "which", lambda name: None)

    result = download_core.download_with_ytdlp_result(
        "https://example.invalid/video", str(tmp_path), audio_only=True)

    assert video.read_bytes() == b"the earlier video"
    assert result.filepath == str(tmp_path / "Clip (1).webm")
    assert (tmp_path / "Clip (1).webm").read_bytes() == b"new audio"
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(download_core.STAGING_PREFIX)]


def test_failed_download_removes_staging_folder(tmp_path, monkeypatch):
    class FailingYDL:
        def __init__(self, options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def add_post_processor(self, pp, when="post_process"):
            pass

        def extract_info(self, url, download=True):
            raise RuntimeError("HTTP Error 503")

    monkeypatch.setattr(download_core, "YTDLP_AVAILABLE", True)
    monkeypatch.setattr(download_core.yt_dlp, "YoutubeDL", FailingYDL)
    monkeypatch.setattr(download_core.shutil, "which", lambda name: None)

    try:
        download_core.download_with_ytdlp_result("https://example.invalid/video", str(tmp_path))
    except RuntimeError:
        pass
    assert list(tmp_path.iterdir()) == []


def test_reserve_unique_path_is_race_free(tmp_path):
    """Concurrent finishers of same-named files must each get their own destination."""
    import threading

    target = str(tmp_path / "Same.mp4")
    results, barrier = [], threading.Barrier(8)

    def claim():
        barrier.wait()
        results.append(download_core._reserve_unique_path(target))

    threads = [threading.Thread(target=claim) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(results)) == 8
    assert str(tmp_path / "Same.mp4") in results
    assert str(tmp_path / "Same (7).mp4") in results


@pytest.mark.parametrize("template", ["%(title)s", "%(upload_date)s_%(title)s", "%(uploader)s/%(title)s", ""])
def test_validate_filename_template_accepts_relative_templates(template):
    assert download_core.validate_filename_template(template) == template


@pytest.mark.parametrize("template", [
    "../%(title)s", "a/../../%(title)s", "a\\..\\%(title)s", "/tmp/%(title)s", "\\%(title)s",
    "C:%(title)s", "c:\\x\\%(title)s",
])
def test_validate_filename_template_rejects_escapes(template):
    with pytest.raises(download_core.UnsafeOutputPath):
        download_core.validate_filename_template(template)


@pytest.fixture
def media_url():
    """A tiny local "video" so the real yt-dlp pipeline can run without the internet."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"\0" * 2048
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/media.mp4"
    server.shutdown()


def _use_fake_extractor(monkeypatch, title):
    """Real YoutubeDL (format selection, filenames, download), with metadata reporting `title`."""

    class FakeExtractorYDL(download_core.yt_dlp.YoutubeDL):
        def extract_info(self, url, download=True, **kwargs):
            return self.process_ie_result({
                "id": "vid", "title": title, "url": url, "ext": "mp4",
                "extractor": "test", "extractor_key": "Test", "webpage_url": url,
            }, download=download)

    monkeypatch.setattr(download_core.yt_dlp, "YoutubeDL", FakeExtractorYDL)


def test_real_download_keeps_subfolder_templates(tmp_path, monkeypatch, media_url):
    _use_fake_extractor(monkeypatch, "Clip")
    out = tmp_path / "out"

    result = download_core.download_with_ytdlp_result(
        media_url, str(out), filename_template="%(title)s/%(id)s")

    assert result.filepath == str(out / "Clip" / "vid.mp4")
    assert os.path.getsize(result.filepath) == 2048


@pytest.mark.parametrize("title, template", [
    ("..", "%(title)s/%(id)s"),          # harmless-looking template, hostile metadata
    ("Clip", "../../%(title)s"),
    ("Clip", "ABSOLUTE"),
])
def test_download_never_writes_outside_output_folder(tmp_path, monkeypatch, media_url, title, template):
    if template == "ABSOLUTE":
        template = str(tmp_path / "elsewhere" / "%(title)s")
    _use_fake_extractor(monkeypatch, title)
    out = tmp_path / "out"

    with pytest.raises(download_core.UnsafeOutputPath):
        download_core.download_with_ytdlp_result(media_url, str(out), filename_template=template)

    # Refused before yt-dlp created any file or folder, and staging was cleaned up
    assert [p.relative_to(tmp_path) for p in tmp_path.rglob("*")] == [out.relative_to(tmp_path)]
