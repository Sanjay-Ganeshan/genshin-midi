import os
import subprocess

MUSE = "D:\\Program Files (x86)\\MuseScore 3\\bin\\MuseScore3.exe"
conversion_dir = "D:\\OneDrive\\Sheet Music\\MuseScoreDownloads\\MIDI"

def convert(mscz_file: str) -> str:
    base = os.path.basename(mscz_file)
    name, ext = os.path.splitext(base)
    assert ext == ".mscz", "Not a musescore file"
    output_file = os.path.join(conversion_dir, f"{name}.mid")
    if not os.path.exists(output_file):
        subprocess.run(
            [
                MUSE,
                "-o",
                output_file,
                os.path.abspath(mscz_file)
            ]
        )
    
    return output_file