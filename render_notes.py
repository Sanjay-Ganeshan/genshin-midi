import threading
import win32api
import win32con
import win32gui

import typing as T
import pygame
import pygame.midi
import numpy as np
import time
pygame.init()
pygame.midi.init()

from read_notes import read_midi_file, discover_files

TRANSPARENT_BACKGROUND = (255, 0, 128)
KEY_COLOR = (240, 240, 240)
PRESSED_COLOR = (127, 127, 127)
FONT_COLOR = (0, 0, 0)

MIDDLE_C = 60
OCTAVE_SEMITONES = 12
LOWEST_NOTE = MIDDLE_C - OCTAVE_SEMITONES
HIGHEST_NOTE = MIDDLE_C + OCTAVE_SEMITONES

# Lowest to highest
KEYBOARD_LETTERS = [
    "ZXCVBNM",
    "ASDFGHJ",
    "QWERTYU",
]
KEYBOARD_LETTERS_WITH_SKIPS = [
    "Z_X_CV_B_N_M",
    "A_S_DF_G_H_J",
    "Q_W_ER_T_Y_U",
]
N_PLAYABLE_OCTAVES = 3
N_NOTES_PER_ROW = 7

def make_window_transparent():
    # Create layered window
    hwnd = pygame.display.get_wm_info()["window"]
    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE,
                        win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) | win32con.WS_EX_LAYERED)
    # Set window transparency color
    win32gui.SetLayeredWindowAttributes(hwnd, win32api.RGB(*TRANSPARENT_BACKGROUND), 0, win32con.LWA_COLORKEY)


def midi_pitch_to_name(pitch: int) -> T.Optional[str]:
    names = "A_BC_D_EF_G_"
    ref_a = MIDDLE_C - 3
    offset = (pitch - ref_a) % len(names)
    the_name = names[offset]
    if the_name == '_':
        return None
    else:
        return the_name

def midi_pitch_to_keyboard(pitch: int) -> T.Optional[str]:
    n_notes = sum(len(l) for l in KEYBOARD_LETTERS_WITH_SKIPS)
    offset = pitch - LOWEST_NOTE


    if offset < 0 or offset >= n_notes:
        return None
    else:
        name = KEYBOARD_LETTERS_WITH_SKIPS[offset // OCTAVE_SEMITONES][offset % OCTAVE_SEMITONES]
        assert name != "_", f"Bad pitch: {pitch}"
        return name


class KeySquare:
    def __init__(self, game: "MIDIRenderer", midi_key: int, norm_xpos: float, norm_ypos: float):
        self.game: "MIDIRenderer" = game
        self.midi_key: int = midi_key
        key_name = midi_pitch_to_keyboard(self.midi_key)
        assert key_name is not None, f"Bad key {self.midi_key}"
        self.keyboard_key_name: str = key_name
        self.keyboard_key: int = pygame.key.key_code(self.keyboard_key_name)
        self.when: T.List[float] = []
        self.norm_xpos: float = norm_xpos
        self.norm_ypos: float = norm_ypos

        m_pitch = midi_pitch_to_name(self.midi_key)
        assert m_pitch is not None, "no sharps or flats"
        self._pitch_name = m_pitch

        self.is_really_down: bool = False
        self.should_be_down: bool = False

    def update(self, now: float) -> None:
        while len(self.when) > 0 and self.when[-1] <= now:
            self.when.pop()
            self.real_toggle()


    def draw(self, now: float) -> None:
        width, height = self.game.norm_size_to_abs(self.game.key_size)
        left, top = self.game.norm_pos_to_abs((self.norm_xpos, self.norm_ypos), (width, height))
        disp = pygame.display.get_surface()
        pygame.draw.rect(disp, PRESSED_COLOR if (self.is_really_down) else KEY_COLOR, pygame.Rect(left, top, width, height))
        rendered_text = self.game.font.render(self.keyboard_key_name, True, FONT_COLOR, None)
        width, height = rendered_text.get_size()
        left, top = self.game.norm_pos_to_abs((self.norm_xpos, self.norm_ypos), (width, height))
        disp.blit(rendered_text, pygame.Rect(left, top, width, height), None)

    def real_down(self):
        if not self.is_really_down:
            self.is_really_down = True
            self.game.out_sounds.note_on(self.midi_key, 127, 0)
    
    def real_up(self):
        if self.is_really_down:
            self.is_really_down = False
            self.game.out_sounds.note_off(self.midi_key, 127, 0)

    def real_toggle(self):
        if self.is_really_down:
            self.real_up()
        else:
            self.real_down()


class MIDIRenderer():
    def __init__(self):
        self.is_done = False
        self.window_size: T.Tuple[int, int] = pygame.display.get_window_size()
        self.mouse_pos: T.Tuple[int, int] = pygame.mouse.get_pos()
        self.key_size: float = (0.05, 0.08)
        self.keys: T.Dict[int, KeySquare] = {}
        self.now: float = 0.0
        self.last_update: T.Optional[float] = None
        self.transpose_amount = -2
        self.known_files: T.Dict[str, str] = discover_files()
        out_port = pygame.midi.get_default_output_id()
        in_port = pygame.midi.get_default_input_id()
        self.in_sounds: T.Optional[pygame.midi.Input] = None
        if in_port != -1:
            self.in_sounds = pygame.midi.Input(in_port)
            print("Now listening to", pygame.midi.get_device_info(in_port))
        self.out_sounds = pygame.midi.Output(out_port, 0)

        self.font = pygame.font.Font(pygame.font.get_default_font(), 32)

        self._setup_keys()

    def _setup_keys(self):
        left_norm = 0.10
        right_norm = 0.90
        top_norm = 0.5
        bottom_norm = 0.85

        center_xs = np.linspace(left_norm, right_norm, N_PLAYABLE_OCTAVES * N_NOTES_PER_ROW, endpoint=True)
        center_ys = np.linspace(bottom_norm, top_norm, N_PLAYABLE_OCTAVES, endpoint=True)

        pitch = LOWEST_NOTE
        for row in range(N_PLAYABLE_OCTAVES):
            real_col = 0
            for column in range(len(KEYBOARD_LETTERS_WITH_SKIPS[row])):
                note_keypress = KEYBOARD_LETTERS_WITH_SKIPS[row][column]
                if note_keypress != "_":
                    self.keys[pitch] = KeySquare(
                        self,
                        pitch,

                        center_xs[(real_col * N_PLAYABLE_OCTAVES) + (2 - row)], 
                        center_ys[row],
                    )
                    real_col += 1
                pitch += 1

    def _transform_pitch(self, pitch: int) -> int:
        return self.transpose_amount + pitch

    def enqueue_file(self, name: str):
        # Throw error is OK
        fn = self.known_files[name]
        self.now = 0
        notes = read_midi_file(fn)
        for k_id in self.keys:
            self.keys[k_id].when.clear()
            self.keys[k_id].real_up()

        for (what, when) in sorted(notes, key=lambda ww: ww[1], reverse=True):
            what = self._transform_pitch(what)
            the_key = self.keys.get(what, None)
            if the_key is not None:
                the_key.when.append(when)


    def update(self):
        nowtime = time.time()

        if self.last_update is not None:
            elapsed = nowtime - self.last_update
            self.now = self.now + elapsed

        self.last_update = nowtime

        self.window_size = pygame.display.get_window_size()
        self.mouse_pos = pygame.mouse.get_pos()
        
        for ev in pygame.event.get():
            if ev.type == pygame.WINDOWCLOSE:
                self.is_done = True
                break

            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    self.is_done = True
                    break
            
                for k_id in self.keys:
                    k = self.keys[k_id]
                    if k.keyboard_key == ev.key:
                        k.real_down()
            
            elif ev.type == pygame.KEYUP:
                for k_id in self.keys:
                    k = self.keys[k_id]
                    if k.keyboard_key == ev.key:
                        k.real_up()
            
        if self.in_sounds is not None:
            toggled_pitches = []
            if self.in_sounds.poll():
                midi_events = self.in_sounds.read(10)
                for ((status, data1, data2, data3), timestamp) in midi_events:
                    if status == 144:
                        # Note on / off get jumbled
                        pitch = data1
                        velocity = data2
                        toggled_pitches.append(pitch)

            # Transform pitches as needed
            for pitch in toggled_pitches:
                tr = self._transform_pitch(pitch)
                matching_key = self.keys.get(tr, None)
                if matching_key is not None:
                    matching_key.real_toggle()
        
        for k_id in self.keys:
            self.keys[k_id].update(self.now)

    def norm_pos_to_abs(self, norm_pos: T.Tuple[float, float], rect_size: T.Optional[T.Tuple[int, int]] = None) -> T.Tuple[int, int]:
        if rect_size is None:
            rect_size = (0, 0)
        rect_x, rect_y = rect_size
        rect_halfx, rect_halfy = rect_x // 2, rect_y // 2
        norm_x, norm_y = norm_pos
        abs_x, abs_y = int(norm_x * self.window_size[0]), int(norm_y * self.window_size[1])
        off_x, off_y = max(0, abs_x - rect_halfx), max(0, abs_y - rect_halfy)
        return off_x, off_y
    
    def norm_size_to_abs(self, norm_size: T.Tuple[float, float]) -> T.Tuple[int, int]:
        norm_w, norm_h = norm_size
        abs_w, abs_h = int(norm_w * self.window_size[0]), int(norm_h * self.window_size[1])
        return abs_w, abs_h

    def draw(self):
        display = pygame.display.get_surface()
        display.fill(TRANSPARENT_BACKGROUND)
        for k_id in self.keys:
            key = self.keys[k_id]
            key.draw(self.now)
        pygame.display.flip()

    def start(self):
        self.now = 0.0
        while True:
            self.update()
            
            if self.is_done:
                break

            self.draw()

            nowtime = time.time() - self.last_update
            time.sleep(0.01)


def main():
    NO_FRAME = False
    if NO_FRAME:
        window_flags = pygame.RESIZABLE | pygame.NOFRAME
    else:
        window_flags = pygame.RESIZABLE
    pygame.display.set_mode((640, 480), window_flags)
    make_window_transparent()
    game = MIDIRenderer()
    game.enqueue_file("barricades")
    game.start()


if __name__ == "__main__":
    main()