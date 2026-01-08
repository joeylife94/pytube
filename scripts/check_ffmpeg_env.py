import os
import shutil
print('FFMPEG_LOCATION->', os.environ.get('FFMPEG_LOCATION'))
print('ffmpeg on PATH->', shutil.which('ffmpeg'))
