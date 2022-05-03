import mido
from mido.midifiles.midifiles import MidiFile
mido.set_backend('mido.backends.rtmidi_python')

import os
import typing as T

def read_midi_file(fname: str) -> T.List[T.Tuple[int, float]]:
    mid = mido.MidiFile(fname)
    all_notes: T.List[T.Tuple[int, float]] = []
    t = 0
    for msg in mid:
        if msg.type == 'note_on' or msg.type == 'note_off':
            which = msg.note
            t += msg.time
            when = t
            all_notes.append((which, when))
    return all_notes


def discover_files() -> T.Dict[str, str]:
    sources = [
        "D:\\Software\\Code\\PythonScripts\\MIDI\\midi_control\\data"
    ]

    all_found: T.Dict[str, str] = {}

    for each_dir in sources:
        each_dir = os.path.abspath(each_dir)
        files_in_dir = os.listdir(each_dir)
        for each_file in files_in_dir:
            bn, ext = os.path.splitext(os.path.basename(each_file))
            ext = ext.lower()
            bn = bn.lower()
            if ext == ".mid" or ext == ".midi":
                all_found[bn] = os.path.join(each_dir, each_file)
    
    return all_found


def main():
    print(read_midi_file("D:\\Software\\Code\\PythonScripts\\MIDI\\midi_control\\data\\Barricades.mid"))

if __name__ == "__main__":
    main()