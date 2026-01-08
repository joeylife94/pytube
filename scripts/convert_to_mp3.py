import sys
import subprocess
import shutil

if len(sys.argv) < 3:
    print('Usage: convert_to_mp3.py <infile> <outfile>')
    sys.exit(2)

infile = sys.argv[1]
outfile = sys.argv[2]

ff = shutil.which('ffmpeg')
if not ff:
    print('ffmpeg not found on PATH')
    sys.exit(1)

cmd = [ff, '-y', '-i', infile, '-vn', '-ab', '192k', '-ar', '44100', outfile]
print('Running:', ' '.join(cmd))
ret = subprocess.run(cmd)
sys.exit(ret.returncode)
