"""
YouTube Downloader Manager
Orchestrates downloads using pytube and yt-dlp with intelligent engine selection.
Supports batch downloads, MP3 conversion, video+subtitles, and subtitles-only modes.
"""

import os
import logging
import shutil
from typing import List, Dict, Any, Optional
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum

from download_core import YTDLP_AVAILABLE, download_with_ytdlp_result

# Third-party imports
try:
    from pytube import YouTube
    PYTUBE_AVAILABLE = True
except ImportError:
    PYTUBE_AVAILABLE = False
    logging.warning("pytube not available - will use yt-dlp exclusively")

if not YTDLP_AVAILABLE:
    logging.warning("yt-dlp not available")


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DownloadMode(Enum):
    """Download mode enumeration"""
    VIDEO = "video"
    MP3 = "mp3"
    VIDEO_SUBS = "video_subs"
    SUBS_ONLY = "subs_only"


class DownloadEngine(Enum):
    """Download engine enumeration"""
    PYTUBE = "pytube"
    YTDLP = "yt-dlp"


class DownloadResult:
    """Container for download results"""
    def __init__(self, url: str, success: bool, file_path: Optional[str] = None, 
                 error: Optional[str] = None, engine: Optional[str] = None):
        self.url = url
        self.success = success
        self.file_path = file_path
        self.error = error
        self.engine = engine

    def __repr__(self):
        status = "SUCCESS" if self.success else "FAILED"
        return f"<DownloadResult {status} url={self.url} engine={self.engine}>"


class YoutubeDownloader:
    """
    Core downloader class that handles individual video downloads.
    Supports both pytube and yt-dlp backends with automatic engine selection.
    """
    
    def __init__(self, output_dir: str = "downloads", preferred_engine: str = "pytube",
                 cookies_from_browser: Optional[str] = None):
        """
        Initialize the downloader.
        
        Args:
            output_dir: Directory where files will be saved
            preferred_engine: Preferred download engine ("pytube" or "yt-dlp")
            cookies_from_browser: Browser name to extract cookies from (e.g. 'chrome', 'firefox')
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cookies_from_browser = cookies_from_browser
        
        # Validate and set preferred engine
        try:
            self.preferred_engine = DownloadEngine(preferred_engine)
        except ValueError:
            logger.warning(f"Invalid engine '{preferred_engine}', defaulting to 'yt-dlp'")
            self.preferred_engine = DownloadEngine.YTDLP
        
        logger.info(f"Initialized YoutubeDownloader with output_dir={output_dir}, "
                   f"preferred_engine={self.preferred_engine.value}")

    def _select_engine(self, mode: DownloadMode) -> DownloadEngine:
        """
        Select the appropriate download engine based on mode and availability.
        
        CRITICAL RULE: MP3 conversion and subtitle downloads MUST use yt-dlp.
        pytube is unreliable for these features.
        
        Args:
            mode: The download mode
            
        Returns:
            The selected DownloadEngine
        """
        # Force yt-dlp for MP3 and subtitle modes
        if mode in [DownloadMode.MP3, DownloadMode.VIDEO_SUBS, DownloadMode.SUBS_ONLY]:
            logger.info(f"Mode '{mode.value}' requires yt-dlp - forcing engine selection")
            if not YTDLP_AVAILABLE:
                raise RuntimeError("yt-dlp is required for MP3/subtitle downloads but is not installed")
            return DownloadEngine.YTDLP
        
        # For video-only mode, use preferred engine if available
        if self.preferred_engine == DownloadEngine.PYTUBE and PYTUBE_AVAILABLE:
            return DownloadEngine.PYTUBE
        elif YTDLP_AVAILABLE:
            return DownloadEngine.YTDLP
        elif PYTUBE_AVAILABLE:
            return DownloadEngine.PYTUBE
        else:
            raise RuntimeError("No download engine available - install pytube or yt-dlp")

    def _download_with_pytube(self, url: str, mode: DownloadMode) -> DownloadResult:
        """
        Download using pytube (video-only mode).
        
        Args:
            url: YouTube video URL
            mode: Download mode (should be VIDEO only)
            
        Returns:
            DownloadResult object
        """
        try:
            logger.info(f"Downloading with pytube: {url}")
            yt = YouTube(url)
            
            # Select the best progressive stream (video+audio combined)
            stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
            
            if not stream:
                return DownloadResult(url, False, error="No suitable stream found", engine="pytube")
            
            # Download the file
            output_file = stream.download(output_path=str(self.output_dir))
            logger.info(f"Downloaded successfully: {output_file}")
            
            return DownloadResult(url, True, file_path=output_file, engine="pytube")
            
        except Exception as e:
            logger.error(f"pytube download failed for {url}: {str(e)}")
            return DownloadResult(url, False, error=str(e), engine="pytube")

    def _build_ytdlp_opts(self, mode: DownloadMode) -> Dict[str, Any]:
        """Legacy option-inspection helper retained for docs/verification.

        Runtime yt-dlp execution no longer consumes this dictionary; downloads are
        routed through :mod:`download_core`. This method remains only for backwards
        compatibility with the repository's historical verification scripts.
        """
        base_opts = {
            'outtmpl': str(self.output_dir / '%(title)s.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
            'extract_flat': False,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Sec-Fetch-Mode': 'navigate',
            },
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios', 'web'],
                    'player_skip': ['configs'],
                }
            },
            'nocheckcertificate': True,
            'no_check_certificate': True,
            'age_limit': None,
        }

        if self.cookies_from_browser:
            base_opts['cookiesfrombrowser'] = (self.cookies_from_browser,)
        
        if mode == DownloadMode.VIDEO:
            opts = {
                **base_opts,
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'merge_output_format': 'mp4',
            }
        elif mode == DownloadMode.MP3:
            if shutil.which('ffmpeg') is None:
                raise RuntimeError("MP3 conversion requires ffmpeg. Install ffmpeg and ensure it's on PATH (or set FFMPEG_LOCATION).")
            opts = {
                **base_opts,
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'outtmpl': str(self.output_dir / '%(title)s.%(ext)s'),
            }
        elif mode == DownloadMode.VIDEO_SUBS:
            opts = {
                **base_opts,
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'merge_output_format': 'mp4',
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': ['en', 'ko'],
                'subtitlesformat': 'srt/vtt/best',
                'postprocessors': [{
                    'key': 'FFmpegSubtitlesConvertor',
                    'format': 'srt',
                }],
            }
        elif mode == DownloadMode.SUBS_ONLY:
            opts = {
                **base_opts,
                'skip_download': True,
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': ['en', 'ko'],
                'subtitlesformat': 'srt/vtt/best',
                'postprocessors': [{
                    'key': 'FFmpegSubtitlesConvertor',
                    'format': 'srt',
                }],
            }
        else:
            raise ValueError(f"Unknown download mode: {mode}")
        return opts

    def _download_with_ytdlp(self, url: str, mode: DownloadMode) -> DownloadResult:
        """Download via the authoritative :mod:`download_core` yt-dlp path."""
        try:
            logger.info(f"Downloading with yt-dlp core (mode={mode.value}): {url}")

            kwargs: Dict[str, Any] = {
                'cookies_from_browser': self.cookies_from_browser,
            }
            if mode == DownloadMode.MP3:
                kwargs.update(audio_only=True, convert_mp3=True)
            elif mode == DownloadMode.VIDEO_SUBS:
                kwargs.update(
                    subtitle_langs=['en', 'ko'],
                    convert_subtitles_to_srt=True,
                )
            elif mode == DownloadMode.SUBS_ONLY:
                kwargs.update(
                    subtitle_langs=['en', 'ko'],
                    subtitles_only=True,
                    convert_subtitles_to_srt=True,
                )

            core_result = download_with_ytdlp_result(
                url,
                str(self.output_dir),
                **kwargs,
            )
            logger.info(f"Downloaded successfully: {core_result.filepath}")
            return DownloadResult(
                url,
                True,
                file_path=core_result.filepath,
                engine="yt-dlp",
            )
        except Exception as e:
            logger.error(f"yt-dlp download failed for {url}: {str(e)}")
            return DownloadResult(url, False, error=str(e), engine="yt-dlp")

    def download(self, url: str, mode: DownloadMode = DownloadMode.VIDEO) -> DownloadResult:
        """
        Download a single video with the specified mode.
        
        Args:
            url: YouTube video URL
            mode: Download mode (video, mp3, video_subs, subs_only)
            
        Returns:
            DownloadResult object
        """
        try:
            # Select the appropriate engine
            engine = self._select_engine(mode)
            logger.info(f"Selected engine: {engine.value} for mode: {mode.value}")
            
            # Route to the appropriate download method
            if engine == DownloadEngine.PYTUBE:
                return self._download_with_pytube(url, mode)
            else:  # YTDLP
                return self._download_with_ytdlp(url, mode)
                
        except Exception as e:
            logger.error(f"Download failed for {url}: {str(e)}")
            return DownloadResult(url, False, error=str(e))


class DownloaderManager:
    """
    High-level manager class that orchestrates batch downloads with concurrency.
    Provides a clean interface for downloading multiple videos simultaneously.
    """
    
    def __init__(self, output_dir: str = "downloads", preferred_engine: str = "pytube",
                 max_workers: int = 3):
        """
        Initialize the DownloaderManager.
        
        Args:
            output_dir: Directory where files will be saved
            preferred_engine: Preferred download engine ("pytube" or "yt-dlp")
            max_workers: Maximum number of concurrent downloads
        """
        self.downloader = YoutubeDownloader(output_dir, preferred_engine)
        self.max_workers = max_workers
        logger.info(f"Initialized DownloaderManager with max_workers={max_workers}")

    def download_batch(self, urls: List[str], mode: str = "video") -> List[DownloadResult]:
        """
        Download multiple videos concurrently using ThreadPoolExecutor.
        
        This method ensures that one failed download doesn't crash the entire batch.
        Each download runs in its own thread with proper error handling.
        
        Args:
            urls: List of YouTube video URLs
            mode: Download mode ("video", "mp3", "video_subs", "subs_only")
            
        Returns:
            List of DownloadResult objects (one per URL)
        """
        # Convert mode string to enum
        try:
            download_mode = DownloadMode(mode)
        except ValueError:
            logger.error(f"Invalid mode '{mode}', defaulting to 'video'")
            download_mode = DownloadMode.VIDEO
        
        logger.info(f"Starting batch download: {len(urls)} URLs, mode={mode}, "
                   f"max_workers={self.max_workers}")
        
        results = []
        
        # Use ThreadPoolExecutor for concurrent downloads
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all download tasks
            future_to_url = {
                executor.submit(self.downloader.download, url, download_mode): url
                for url in urls
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    result = future.result()
                    results.append(result)
                    
                    if result.success:
                        logger.info(f"✓ Completed: {url}")
                    else:
                        logger.error(f"✗ Failed: {url} - {result.error}")
                        
                except Exception as e:
                    # Catch any unexpected exceptions
                    logger.error(f"✗ Unexpected error for {url}: {str(e)}")
                    results.append(DownloadResult(url, False, error=str(e)))
        
        # Summary
        successful = sum(1 for r in results if r.success)
        logger.info(f"Batch complete: {successful}/{len(urls)} successful")
        
        return results

    def download_single(self, url: str, mode: str = "video") -> DownloadResult:
        """
        Download a single video (convenience method).
        
        Args:
            url: YouTube video URL
            mode: Download mode ("video", "mp3", "video_subs", "subs_only")
            
        Returns:
            DownloadResult object
        """
        try:
            download_mode = DownloadMode(mode)
        except ValueError:
            logger.error(f"Invalid mode '{mode}', defaulting to 'video'")
            download_mode = DownloadMode.VIDEO
        
        return self.downloader.download(url, download_mode)


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

def example_usage():
    """Demonstrate various usage patterns of the DownloaderManager"""
    
    # Example URLs (replace with real URLs for testing)
    urls = [
        "https://youtu.be/dQw4w9WgXcQ",
        "https://youtu.be/jNQXAC9IVRw",
        "https://youtu.be/9bZkp7q19f0",
    ]
    
    # ------------------------------------------------------------------------
    # Example 1: Batch video download (uses preferred engine if possible)
    # ------------------------------------------------------------------------
    print("\n" + "="*70)
    print("Example 1: Batch Video Download")
    print("="*70)
    
    manager = DownloaderManager(
        output_dir="downloads/videos",
        preferred_engine="pytube",  # Will use pytube for plain video downloads
        max_workers=3
    )
    
    results = manager.download_batch(urls, mode="video")
    
    # Print results
    for result in results:
        if result.success:
            print(f"✓ {result.url} -> {result.file_path}")
        else:
            print(f"✗ {result.url} -> ERROR: {result.error}")
    
    # ------------------------------------------------------------------------
    # Example 2: MP3 Download (automatically uses yt-dlp)
    # ------------------------------------------------------------------------
    print("\n" + "="*70)
    print("Example 2: MP3 Download (forced yt-dlp)")
    print("="*70)
    
    manager_mp3 = DownloaderManager(
        output_dir="downloads/mp3",
        preferred_engine="pytube",  # Will be overridden to yt-dlp for MP3
        max_workers=2
    )
    
    results_mp3 = manager_mp3.download_batch(urls[:2], mode="mp3")
    
    for result in results_mp3:
        print(f"Engine used: {result.engine}")
        if result.success:
            print(f"✓ MP3 saved: {result.file_path}")
    
    # ------------------------------------------------------------------------
    # Example 3: Video + Subtitles (automatically uses yt-dlp)
    # ------------------------------------------------------------------------
    print("\n" + "="*70)
    print("Example 3: Video + Subtitles Download")
    print("="*70)
    
    manager_subs = DownloaderManager(
        output_dir="downloads/with_subs",
        preferred_engine="pytube",  # Will be overridden to yt-dlp
        max_workers=2
    )
    
    result_subs = manager_subs.download_single(urls[0], mode="video_subs")
    print(f"✓ Downloaded with subs: {result_subs.file_path}")
    
    # ------------------------------------------------------------------------
    # Example 4: Subtitles Only (automatically uses yt-dlp)
    # ------------------------------------------------------------------------
    print("\n" + "="*70)
    print("Example 4: Subtitles Only (no video)")
    print("="*70)
    
    manager_subs_only = DownloaderManager(
        output_dir="downloads/subtitles_only",
        preferred_engine="pytube",  # Will be overridden to yt-dlp
        max_workers=2
    )
    
    results_subs_only = manager_subs_only.download_batch(urls, mode="subs_only")
    
    for result in results_subs_only:
        if result.success:
            print(f"✓ Subtitles saved: {result.file_path}")


if __name__ == "__main__":
    # Run the examples
    example_usage()
