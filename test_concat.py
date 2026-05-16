import os
import moviepy.editor as mpy
import imageio_ffmpeg
import subprocess

ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

# Create two dummy clips with audio
clip1 = mpy.ColorClip(size=(640, 360), color=(255, 0, 0), duration=1)
clip1 = clip1.set_audio(mpy.AudioClip(lambda t: [0,0], duration=1, fps=44100))
clip1.write_videofile("test1.mp4", fps=24, codec="libx264", audio_codec="aac", logger=None)
clip1.close()

clip2 = mpy.ColorClip(size=(640, 360), color=(0, 255, 0), duration=1)
clip2 = clip2.set_audio(mpy.AudioClip(lambda t: [0,0], duration=1, fps=44100))
clip2.write_videofile("test2.mp4", fps=24, codec="libx264", audio_codec="aac", logger=None)
clip2.close()

# Concat using ffmpeg
with open("concat.txt", "w") as f:
    f.write("file 'test1.mp4'\n")
    f.write("file 'test2.mp4'\n")

subprocess.run([ffmpeg_path, "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt", "-c", "copy", "master_test.mp4"], check=True)

print("Exists:", os.path.exists("master_test.mp4"))
print("Size:", os.path.getsize("master_test.mp4"))
