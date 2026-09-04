"""Tests for the DownloadQueue -> download_core adapter."""

from download_core import DownloadResult
from download_queue import QueueItem
import queue_download_adapter


def test_queue_adapter_maps_item_options_and_records_history(tmp_path, monkeypatch):
    output = tmp_path / "sample.mp4"
    output.write_bytes(b"video")
    captured = {}
    recorded = {}
    progress = []

    def fake_download(url, output_folder, **kwargs):
        captured["url"] = url
        captured["output_folder"] = output_folder
        captured["kwargs"] = kwargs
        kwargs["progress_callback"]("sample.mp4", 50, 100, 1.0, 1)
        return DownloadResult(filepath=str(output), title="Sample title")

    def fake_record(url, output_folder, filepath, **kwargs):
        recorded.update({
            "url": url,
            "output_folder": output_folder,
            "filepath": filepath,
            **kwargs,
        })

    monkeypatch.setattr(queue_download_adapter, "download_with_ytdlp_result", fake_download)
    monkeypatch.setattr(queue_download_adapter, "record_download", fake_record)

    item = QueueItem(
        url="https://example.invalid/video",
        output_folder=str(tmp_path),
        audio_only=False,
        subtitles=True,
        subtitle_lang="ko, en",
        rate_limit=256,
        proxy="socks5://127.0.0.1:1080",
        cookiefile=str(tmp_path / "cookies.txt"),
        cookies_from_browser="chrome",
        resolution="1080p",
        filename_template="%(upload_date)s_%(title)s",
    )

    result = queue_download_adapter.download_queue_item(item, progress.append)

    assert result == str(output)
    assert progress == [50]
    assert captured["kwargs"]["subtitle_langs"] == ["ko", "en"]
    assert captured["kwargs"]["rate_limit_kbps"] == 256
    assert captured["kwargs"]["proxy"] == "socks5://127.0.0.1:1080"
    assert captured["kwargs"]["cookies_from_browser"] == "chrome"
    assert captured["kwargs"]["resolution"] == "1080p"
    assert captured["kwargs"]["filename_template"] == "%(upload_date)s_%(title)s"
    assert recorded["title"] == "Sample title"
    assert recorded["size"] == 5
    assert recorded["mode"] == "video"


def test_queue_adapter_records_audio_mode_for_mp3(tmp_path, monkeypatch):
    output = tmp_path / "sample.mp3"
    output.write_bytes(b"audio")
    recorded = {}

    monkeypatch.setattr(
        queue_download_adapter,
        "download_with_ytdlp_result",
        lambda *args, **kwargs: DownloadResult(filepath=str(output), title="Audio"),
    )
    monkeypatch.setattr(
        queue_download_adapter,
        "record_download",
        lambda *args, **kwargs: recorded.update(kwargs),
    )

    item = QueueItem(
        url="https://example.invalid/audio",
        output_folder=str(tmp_path),
        audio_only=True,
        convert_mp3=True,
    )

    queue_download_adapter.download_queue_item(item, lambda _pct: None)
    assert recorded["mode"] == "audio"
