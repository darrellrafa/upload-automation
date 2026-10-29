import os
import subprocess

FFMPEG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "ffmpeg")

# 1. Create a 3-second dummy mp4 video with color lavfi
test_video = "scratch/test_video.mp4"
cmd_create_video = [
    FFMPEG_PATH, "-y",
    "-f", "lavfi", "-i", "color=c=navy:s=1080x1920:d=3",
    "-c:v", "libx264", "-t", "3", "-pix_fmt", "yuv420p",
    test_video
]
subprocess.run(cmd_create_video, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print("Dummy 3s video created:", os.path.exists(test_video), os.path.getsize(test_video), "bytes")

# 2. Merge with downloaded audio
audio_track = "audio_tracks/Get Outside! - Jason Farnham.mp3"
merged_video = "scratch/test_merged_with_audio.mp4"

cmd_merge = [
    FFMPEG_PATH, "-y",
    "-i", test_video,
    "-i", audio_track,
    "-c:v", "copy",
    "-c:a", "aac",
    "-b:a", "192k",
    "-map", "0:v:0",
    "-map", "1:a:0",
    "-shortest",
    merged_video
]
subprocess.run(cmd_merge, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print("Merged video created:", os.path.exists(merged_video), os.path.getsize(merged_video), "bytes")

# Probe merged video
ffprobe = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "ffprobe")
out = subprocess.check_output([ffprobe, merged_video], stderr=subprocess.STDOUT).decode()
for line in out.splitlines():
    if "Stream #" in line or "Duration:" in line:
        print(" ", line.strip())

# Cleanup test files
os.remove(test_video)
os.remove(merged_video)
print("Cleanup done!")
