"""
Test suite and demonstration for DownloaderManager.
Shows practical usage examples with real scenarios.
"""

import sys
import logging
from pathlib import Path

# Import the DownloaderManager
from downloader_manager import DownloaderManager, DownloadMode

# Configure logging to see detailed output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_scenario_1_basic_video_download():
    """
    Scenario 1: Basic video download with pytube preference.
    Expected: Should try pytube first for plain video downloads.
    """
    print("\n" + "="*80)
    print("SCENARIO 1: Basic Video Download (Preferred Engine: pytube)")
    print("="*80)
    
    urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # Classic test video
    ]
    
    manager = DownloaderManager(
        output_dir="downloads/test_scenario_1",
        preferred_engine="pytube",
        max_workers=1
    )
    
    results = manager.download_batch(urls, mode="video")
    
    # Validate results
    for result in results:
        print(f"\nURL: {result.url}")
        print(f"Success: {result.success}")
        print(f"Engine Used: {result.engine}")
        print(f"File Path: {result.file_path}")
        print(f"Error: {result.error}")
    
    return results


def test_scenario_2_mp3_conversion():
    """
    Scenario 2: MP3 download with automatic yt-dlp forcing.
    Expected: Should automatically use yt-dlp regardless of preference.
    """
    print("\n" + "="*80)
    print("SCENARIO 2: MP3 Conversion (Auto-forced to yt-dlp)")
    print("="*80)
    
    urls = [
        "https://www.youtube.com/watch?v=jNQXAC9IVRw",  # Another test video
    ]
    
    manager = DownloaderManager(
        output_dir="downloads/test_scenario_2_mp3",
        preferred_engine="pytube",  # Will be overridden!
        max_workers=1
    )
    
    results = manager.download_batch(urls, mode="mp3")
    
    for result in results:
        print(f"\nURL: {result.url}")
        print(f"Success: {result.success}")
        print(f"Engine Used: {result.engine}")
        assert result.engine == "yt-dlp", "MP3 mode should force yt-dlp!"
        print(f"File Path: {result.file_path}")
        
        # Verify MP3 file exists
        if result.success and result.file_path:
            assert ".mp3" in result.file_path, "Output should be MP3 format"
    
    return results


def test_scenario_3_video_with_subtitles():
    """
    Scenario 3: Download video + subtitles.
    Expected: Should use yt-dlp and download both video and subtitle files.
    """
    print("\n" + "="*80)
    print("SCENARIO 3: Video + Subtitles Download")
    print("="*80)
    
    # Use a video known to have subtitles
    urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ]
    
    manager = DownloaderManager(
        output_dir="downloads/test_scenario_3_video_subs",
        preferred_engine="pytube",  # Will be overridden!
        max_workers=1
    )
    
    result = manager.download_single(urls[0], mode="video_subs")
    
    print(f"\nURL: {result.url}")
    print(f"Success: {result.success}")
    print(f"Engine Used: {result.engine}")
    assert result.engine == "yt-dlp", "video_subs mode should force yt-dlp!"
    print(f"File Path: {result.file_path}")
    
    # Check for subtitle files in the output directory
    if result.success:
        output_dir = Path("downloads/test_scenario_3_video_subs")
        subtitle_files = list(output_dir.glob("*.srt")) + list(output_dir.glob("*.vtt"))
        print(f"Subtitle files found: {len(subtitle_files)}")
        for sub_file in subtitle_files:
            print(f"  - {sub_file.name}")
    
    return result


def test_scenario_4_subtitles_only():
    """
    Scenario 4: Download ONLY subtitles (skip video/audio).
    Expected: Should use yt-dlp and download only subtitle files.
    """
    print("\n" + "="*80)
    print("SCENARIO 4: Subtitles Only (No Video/Audio)")
    print("="*80)
    
    urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ]
    
    manager = DownloaderManager(
        output_dir="downloads/test_scenario_4_subs_only",
        preferred_engine="pytube",  # Will be overridden!
        max_workers=1
    )
    
    results = manager.download_batch(urls, mode="subs_only")
    
    for result in results:
        print(f"\nURL: {result.url}")
        print(f"Success: {result.success}")
        print(f"Engine Used: {result.engine}")
        assert result.engine == "yt-dlp", "subs_only mode should force yt-dlp!"
        
        # Check that no video files were downloaded
        if result.success:
            output_dir = Path("downloads/test_scenario_4_subs_only")
            video_files = list(output_dir.glob("*.mp4")) + list(output_dir.glob("*.webm"))
            subtitle_files = list(output_dir.glob("*.srt")) + list(output_dir.glob("*.vtt"))
            
            print(f"Video files: {len(video_files)} (should be 0)")
            print(f"Subtitle files: {len(subtitle_files)}")
            
            for sub_file in subtitle_files:
                print(f"  - {sub_file.name}")
    
    return results


def test_scenario_5_batch_concurrent():
    """
    Scenario 5: Batch download with concurrency.
    Expected: Downloads should run concurrently, errors in one shouldn't crash others.
    """
    print("\n" + "="*80)
    print("SCENARIO 5: Batch Concurrent Download (3 workers)")
    print("="*80)
    
    urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        "https://www.youtube.com/watch?v=9bZkp7q19f0",
        "https://invalid-url-that-will-fail",  # Intentional failure
    ]
    
    manager = DownloaderManager(
        output_dir="downloads/test_scenario_5_batch",
        preferred_engine="yt-dlp",
        max_workers=3  # 3 concurrent downloads
    )
    
    results = manager.download_batch(urls, mode="video")
    
    # Summary
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    
    print(f"\n{'='*80}")
    print(f"SUMMARY: {len(successful)}/{len(urls)} successful")
    print(f"{'='*80}")
    
    print("\n✓ Successful downloads:")
    for result in successful:
        print(f"  - {result.url}")
        print(f"    Engine: {result.engine}, File: {result.file_path}")
    
    print("\n✗ Failed downloads:")
    for result in failed:
        print(f"  - {result.url}")
        print(f"    Error: {result.error}")
    
    # Verify that at least some succeeded despite one failure
    assert len(successful) > 0, "At least some downloads should succeed"
    assert len(failed) > 0, "The invalid URL should fail"
    
    return results


def test_scenario_6_engine_selection_logic():
    """
    Scenario 6: Verify engine selection logic.
    Test that the hybrid engine logic works correctly.
    """
    print("\n" + "="*80)
    print("SCENARIO 6: Engine Selection Logic Verification")
    print("="*80)
    
    from downloader_manager import YoutubeDownloader
    
    downloader = YoutubeDownloader(
        output_dir="downloads/test_scenario_6",
        preferred_engine="pytube"
    )
    
    # Test engine selection for each mode
    modes = [
        (DownloadMode.VIDEO, "Should use preferred (pytube if available)"),
        (DownloadMode.MP3, "Should FORCE yt-dlp"),
        (DownloadMode.VIDEO_SUBS, "Should FORCE yt-dlp"),
        (DownloadMode.SUBS_ONLY, "Should FORCE yt-dlp"),
    ]
    
    for mode, description in modes:
        engine = downloader._select_engine(mode)
        print(f"\nMode: {mode.value:15} -> Engine: {engine.value:10} | {description}")
        
        # Verify forcing logic
        if mode in [DownloadMode.MP3, DownloadMode.VIDEO_SUBS, DownloadMode.SUBS_ONLY]:
            assert engine.value == "yt-dlp", f"Mode {mode.value} should force yt-dlp!"


def main():
    """Run all test scenarios"""
    print("\n" + "="*80)
    print("DOWNLOADER MANAGER TEST SUITE")
    print("="*80)
    
    # Check dependencies
    try:
        import yt_dlp
        print("✓ yt-dlp is installed")
    except ImportError:
        print("✗ yt-dlp is NOT installed - install with: pip install yt-dlp")
        return
    
    try:
        from pytube import YouTube
        print("✓ pytube is installed")
    except ImportError:
        print("⚠ pytube is NOT installed (optional) - install with: pip install pytube")
    
    # Run scenarios (comment out scenarios you don't want to run)
    try:
        # Quick tests (no actual downloads)
        test_scenario_6_engine_selection_logic()
        
        # Actual download tests (uncomment to run)
        # WARNING: These will download real videos - use carefully!
        
        # test_scenario_1_basic_video_download()
        # test_scenario_2_mp3_conversion()
        # test_scenario_3_video_with_subtitles()
        # test_scenario_4_subtitles_only()
        # test_scenario_5_batch_concurrent()
        
        print("\n" + "="*80)
        print("ALL TESTS COMPLETED")
        print("="*80)
        
    except Exception as e:
        logger.error(f"Test failed with error: {str(e)}", exc_info=True)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
