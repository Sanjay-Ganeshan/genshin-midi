import mido
from mido.midifiles.midifiles import DEFAULT_TICKS_PER_BEAT, DEFAULT_TEMPO
mido.set_backend('mido.backends.rtmidi_python')

import os
import typing as T

RECORDINGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recordings")

def read_midi_file(fname: str) -> T.List[T.Tuple[int, float]]:
    print("Reading", fname)
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


def _apply_penalty(freq: T.List[int], penalty: T.List[int], rshift: int) -> int:
    assert len(freq) == len(penalty), "Not parallel"
    pen = 0
    for i in range(len(freq)):
        f_ix = (i + rshift) % len(freq)
        pen += penalty[i] * freq[f_ix]
    return pen


def autotranspose(notes: T.List[T.Tuple[int, float]]) -> int:
    freq = [0] * 12 #  A  #  B  C  #  D  #  E  F  #  G  #
    penalty =           [0, 1, 0, 0, 1, 0, 1, 0, 0, 1, 0, 1]
    distance =          [0, -1, -2, -3, -4, -5, -6, 5, 4, 3, 2, 1]
    base = 57 # Some A
    
    for (pitch, _) in notes:
        offset = (pitch - base) % len(freq)
        freq[offset] += 1

    # Now, find which circ is the best / has the lowest penalty
    shift_and_pen: T.List[T.Tuple[int, int]] = []
    for rshift in range(len(freq)):
        pen = _apply_penalty(freq, penalty, rshift)
        shift_and_pen.append((distance[rshift], pen))
    
    shift_and_pen.sort(key=lambda sp: (sp[1], abs(sp[0])))
    best_shift, best_penalty = shift_and_pen[0]
    score = (len(notes)-best_penalty)/len(notes)
    return best_shift, score

def dump_midi_file(notes: T.List[T.Tuple[int, float]], fname: T.Optional[str] = None) -> str:
    if fname is None:
        r_id = 0
        while os.path.exists(fname := os.path.join(RECORDINGS, f"recording_{r_id}.midi")):
            r_id += 1
    
    f = mido.MidiFile(type=0) # 0 - single channel, 1 - sync channels, 2 - async channels
    track = f.add_track("main")
    held_pitches = set()
    last_time = 0
    for (what, when) in sorted(notes, key = lambda what_and_when: what_and_when[1]):
        if what in held_pitches:
            msg_type = "note_off"
            held_pitches.remove(what)
        else:
            msg_type = "note_on"
            held_pitches.add(what)
        # when is in abs time, we need it in tick-delta time
        delta_seconds = when - last_time
        last_time = when
        # Convert to ticks. 1 beat = 1 second
        n_ticks = mido.second2tick(delta_seconds, DEFAULT_TICKS_PER_BEAT, DEFAULT_TEMPO)

        msg = mido.Message(type=msg_type, note=what, velocity=127, time=int(n_ticks))
        track.append(msg)
    f.save(fname)
    return fname


def discover_files() -> T.Dict[str, str]:
    sources = [
        "D:\\Software\\Code\\PythonScripts\\MIDI\\midi_control\\data",
        "D:\\OneDrive\\Sheet Music\\MuseScoreDownloads\\MIDI",
        "D:\\OneDrive\\Sheet Music\\Piano Music\\Piano Music\\MIDIs"
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