import os
import subprocess

MUSE = "D:\\Program Files\\MuseScore 3\\bin\\MuseScore3.exe"
conversion_dir = "D:\\OneDrive\\Sheet Music\\MuseScoreDownloads\\MIDI"

def convert(mscz_file: str) -> str:
    base = os.path.basename(mscz_file)
    name, ext = os.path.splitext(base)
    assert ext == ".mscz", "Not a musescore file"
    output_file = os.path.join(conversion_dir, f"{name}.mid")
    if not os.path.exists(output_file):
        proc = subprocess.run(
            [
                MUSE,
                "-o",
                output_file,
                os.path.abspath(mscz_file)
            ],
            capture_output=True
        )
        if not proc.returncode == 0:
            print(proc.stdout)
            print(proc.stderr)
            proc.check_returncode()

    return output_file