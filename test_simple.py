"""
간단한 비디오 다운로드 테스트 (자막 없이)
"""

from downloader_manager import DownloaderManager
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

print("\n" + "="*70)
print("  간단한 비디오 다운로드 테스트")
print("="*70)

# 테스트 URL
url = "https://youtu.be/nuQwmCtn7PM"

print(f"\n📥 URL: {url}")
print(f"   모드: video (간단한 비디오 다운로드)")

manager = DownloaderManager(
    output_dir="downloads/simple_video",
    preferred_engine="yt-dlp",
    max_workers=1
)

print("\n다운로드 시작...\n")
result = manager.download_single(url, mode="video")

print("\n" + "="*70)
if result.success:
    print("✅ 성공!")
    print(f"   파일: {result.file_path}")
    print(f"   엔진: {result.engine}")
    
    # 파일 크기 확인
    import os
    if result.file_path and os.path.exists(result.file_path):
        size_mb = os.path.getsize(result.file_path) / (1024 * 1024)
        print(f"   크기: {size_mb:.2f} MB")
else:
    print("❌ 실패!")
    print(f"   에러: {result.error}")
print("="*70)
