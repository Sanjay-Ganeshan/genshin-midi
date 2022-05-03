import threading
import win32api
import win32con
import win32gui

import typing as T
import pygame
import pygame.midi
import numpy as np
from dataclasses import dataclass, field
import colorsys
import time
pygame.init()
pygame.midi.init()

from read_notes import autotranspose, read_midi_file, discover_files, dump_midi_file
from interception_py.interception_sender import InterceptionSender

TRANSPARENT_BACKGROUND = (255, 0, 128)
KEY_COLOR = (240, 240, 240)
PRESSED_COLOR = (127, 127, 127)
FONT_COLOR = (0, 0, 0)

MIDDLE_C = 60
OCTAVE_SEMITONES = 12
LOWEST_NOTE = MIDDLE_C - OCTAVE_SEMITONES
HIGHEST_NOTE = MIDDLE_C + (2 * OCTAVE_SEMITONES)

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
MAKE_TRANSPARENT = True

def make_window_transparent():
    # Create layered window
    NOSIZE = 1
    NOMOVE = 2
    TOPMOST = -1
    NOT_TOPMOST = -2
    w, h = pygame.display.get_window_size()
    hwnd = pygame.display.get_wm_info()["window"]
    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE,
                        win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) | win32con.WS_EX_LAYERED)
    # Set window transparency color
    win32gui.SetLayeredWindowAttributes(hwnd, win32api.RGB(*TRANSPARENT_BACKGROUND), 0, win32con.LWA_COLORKEY)
    win32gui.SetWindowPos(hwnd, TOPMOST, 0, 0, w, h, 0)


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


def rgb_norm_to_rgb(rgb_n: T.Tuple[float, float, float]):
    r, g, b = rgb_n
    return (
        min(255, max(0, int(r * 255))),
        min(255, max(0, int(g * 255))),
        min(255, max(0, int(b * 255)))
    )

def get_note_color(
    pitch: int
) -> T.Optional[
        T.Tuple[
            T.Tuple[int, int, int],
            T.Tuple[int, int, int],
            T.Tuple[int, int, int],
        ]
    ]:
    squeeze_into = 0.8
    if pitch < LOWEST_NOTE or pitch > HIGHEST_NOTE:
        print(pitch)
        return None
    else:
        norm_offset = (pitch - LOWEST_NOTE) / (HIGHEST_NOTE - LOWEST_NOTE)
        norm_offset *= squeeze_into
        upcoming = colorsys.hsv_to_rgb(norm_offset, 1.0, 1.0)
        dim = colorsys.hsv_to_rgb(norm_offset, 1.0, 0.4)
        bright = colorsys.hsv_to_rgb(norm_offset, 0.7, 1.0)
        return tuple(map(rgb_norm_to_rgb, [upcoming, dim, bright]))

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
        colors = get_note_color(self.midi_key)
        assert colors is not None
        self.color: T.Tuple[int, int, int]
        self.dim_color: T.Tuple[int, int, int]
        self.bright_color: T.Tuple[int, int, int]
        self.color, self.dim_color, self.bright_color = colors

        m_pitch = midi_pitch_to_name(self.midi_key)
        assert m_pitch is not None, "no sharps or flats"
        self._pitch_name = m_pitch

        self.is_really_down: bool = False
        self.key_is_pressed: bool = False
        self.should_be_down: bool = False
        self.note_on: bool = False

        self.when_ix = 0

    def peek(self) -> T.Optional[float]:
        if self.when_ix < len(self.when):
            return self.when[self.when_ix]
        else:
            return None

        
    def pop(self) -> T.Optional[float]:
        val = self.peek()
        if self.when_ix < len(self.when):
            self.when_ix += 1
        return val



    def update(self, now: float) -> None:
        n_toggles = 0
        while (next_time := self.peek()) is not None and next_time <= now:
            self.pop()
            n_toggles += 1
        
        for n in range(n_toggles):
            self.fake_toggle()
            if self.game.recording_plays:
                self.real_toggle()

    def backout_before(self, now: float) -> None:
        original_when_ix = self.when_ix
        new_when_ix = original_when_ix

        # Find the point where the NEXT action is in the future, and the PREVIOUS
        # action is in the past
        new_when_ix = max(0, new_when_ix)
        while True:
            prev_idx = new_when_ix - 1
            
            if prev_idx < 0 or prev_idx >= len(self.when):
                prev_in_past = True
            else:
                prev_in_past = (self.when[prev_idx] <= now)
            
            if not prev_in_past:
                new_when_ix -= 1
                continue
        
            if new_when_ix < 0 or new_when_ix >= len(self.when):
                next_in_future = True
            else:
                next_in_future = (self.when[new_when_ix] > now)
            
            if not next_in_future:
                new_when_ix += 1
                continue
        
            break
            
        n_toggles = original_when_ix - new_when_ix
        
        # Instead of toggling over and over, we can just determine if it WAS
        # a toggle
        is_toggle = n_toggles % 2 == 1
        if is_toggle:
            self.fake_toggle()
            if self.game.recording_plays:
                self.real_toggle()
        self.when_ix = new_when_ix
                    


    def fake_toggle(self):
        self.should_be_down = not self.should_be_down

    def draw_upcoming_notes(self, now: float, top: int, block_width: int, block_height: int, disp: pygame.Surface):
        drawing_block = self.when_ix
        drawing_is_stop = self.should_be_down
        prev_height = top
        is_first = True
        while drawing_block < len(self.when):
            drawing_at = self.when[drawing_block]
            until_then = drawing_at - now
            assert until_then >= 0, "Shouldn't be in here"
            if drawing_is_stop or until_then < self.game.lookahead:
                norm_until = min(until_then / self.game.lookahead, 1.0)
                norm_height_diff = self.game.lookahead_height * norm_until
                block_norm_ypos = self.norm_ypos - norm_height_diff
                block_left, block_top = self.game.norm_pos_to_abs((self.norm_xpos, block_norm_ypos), (block_width , block_height))
                
                if drawing_is_stop:
                    extend_block_height = prev_height-block_top
                    outline_size = block_width // 7
                    if extend_block_height > outline_size * 2:
                        pygame.draw.rect(disp, self.bright_color, pygame.Rect(block_left, block_top, block_width, extend_block_height), 0, block_width // 3)
                        if is_first and self.is_really_down:
                            pygame.draw.rect(disp, (0,0,0), pygame.Rect(block_left, block_top, block_width, extend_block_height), block_width // 7, block_width // 4)
                else:
                    prev_height = block_top
                
                drawing_block += 1
                drawing_is_stop = not drawing_is_stop
                is_first = False
            else:
                # Everything else is later
                break
    
    def draw_past_notes(self, now: float, top: int, block_width: int, block_height: int, disp: pygame.Surface):
        drawing_block = len(self.when)-1
        drawing_is_stop = self.is_really_down
        prev_height = top
        is_first = True
        while drawing_block >= 0 and drawing_block < len(self.when):
            drawing_at = self.when[drawing_block]
            since_then = now - drawing_at
            assert since_then >= 0, "Shouldn't be in here"
            if drawing_is_stop or since_then < self.game.lookahead:
                norm_since = min(since_then / self.game.lookahead, 1.0)
                norm_height_diff = self.game.lookahead_height * norm_since
                block_norm_ypos = self.norm_ypos - norm_height_diff
                block_left, block_top = self.game.norm_pos_to_abs((self.norm_xpos, block_norm_ypos), (block_width , block_height))
                
                if drawing_is_stop or (is_first and self.is_really_down):
                    extend_block_height = prev_height - block_top
                    outline_size = block_width // 7
                    if extend_block_height > outline_size * 2:
                        pygame.draw.rect(disp, self.bright_color, pygame.Rect(block_left, block_top, block_width, extend_block_height), 0, block_width // 3)
                        if is_first and self.is_really_down:
                            pygame.draw.rect(disp, (0,0,0), pygame.Rect(block_left, block_top, block_width, extend_block_height), block_width // 7, block_width // 4)
                else:
                    prev_height = block_top
                
                drawing_block -= 1
                drawing_is_stop = not drawing_is_stop
                is_first = False
            else:
                # Everything else is later
                break

    def draw(self, now: float) -> None:
        # Get common drawing info
        block_width, block_height = self.game.norm_size_to_abs(self.game.key_size)
        left, top = self.game.norm_pos_to_abs((self.norm_xpos, self.norm_ypos), (block_width, block_height))
        disp = pygame.display.get_surface()

        # Draw upcoming notes

        if self.game.recording_mode and not (self.game.reviewing_recording()):
            self.draw_past_notes(now, top, block_width, block_height, disp)
        else:
            self.draw_upcoming_notes(now, top, block_width, block_height, disp)


        # Draw the key
        pygame.draw.rect(disp, self.dim_color if (self.is_really_down) else self.bright_color, pygame.Rect(left, top, block_width, block_height))

        # Draw the letter on the key
        rendered_text = self.game.font.render((self.keyboard_key_name if self.game.is_staggered else self._pitch_name), True, FONT_COLOR, None)
        txt_width, txt_height = rendered_text.get_size()
        left, top = self.game.norm_pos_to_abs((self.norm_xpos, self.norm_ypos), (txt_width, txt_height))
        disp.blit(rendered_text, pygame.Rect(left, top, txt_width, txt_height), None)

    def real_down(self, was_keypress: bool = False):
        if was_keypress:
            self.key_is_pressed = True
        if not self.is_really_down:
            self.is_really_down = True
            if self.game.play_sounds:
                self.game.out_sounds.note_on(self.midi_key, 127, 0)
                self.note_on = True
            if self.game.macro_output and not was_keypress and not self.game.window_focused:
                assert self.game.ignore_keypresses, "Refuse!"
                self.key_is_pressed = True
                self.game.macro.keyDown(self.keyboard_key_name.lower())
                self.game.macro.keyUp(self.keyboard_key_name.lower())
            if self.game.recording_mode:
                assert self.when_ix == len(self.when), "Still have stuff to play"
                self.when.append(self.game.now)
                self.when_ix += 1
                

    
    def real_up(self, was_keypress: bool = False):
        if was_keypress:
            self.key_is_pressed = False
        if self.is_really_down:
            self.is_really_down = False
            if self.note_on:
                self.game.out_sounds.note_off(self.midi_key, 127, 0)
            
            if self.game.macro_output and not was_keypress and self.key_is_pressed:
                assert self.game.ignore_keypresses, "Refuse!"
                self.key_is_pressed = False
            
            if self.game.recording_mode:
                assert self.when_ix == len(self.when), "Still have stuff to play"
                self.when.append(self.game.now)
                self.when_ix += 1

    def real_toggle(self, was_keypress: bool = False):
        if self.is_really_down:
            self.real_up(was_keypress)
        else:
            self.real_down(was_keypress)

    def okay_to_progress(self) -> bool:
        # It's okay to leave things on, but not to have them off
        return (not self.should_be_down) or (self.should_be_down and self.is_really_down)

    def dump(self) -> T.List[T.Tuple[int, float]]:
        return [(self.midi_key, when) for when in self.when]


@dataclass
class GameSettings:
    recording_plays: bool = field(default=True)
    keep_in_bounds: bool = field(default=True)
    macro_output: bool = field(default=True)
    ignore_keypresses: bool = field(default=False)
    play_sounds: bool = field(default=True)
    key_size: T.Tuple[float, float] = field(default=(0.035, 0.08))
    lookahead: float = field(default=1.0)
    lookahead_height: float = field(default=0.42)
    timescale: float = field(default=1.0)
    paused: bool = field(default=True) # Do we start paused?
    progression_mode: bool = field(default=False)

    transpose_amount = 0

    def __post_init__(self):
        if self.macro_output:
            self.ignore_keypresses = True



class MIDIRenderer():
    def __init__(self, preset: T.Optional[GameSettings] = None):
        # Settings
        self.settings = preset or GameSettings()
        
        # Properties - these are determined / adjusted
        self.now: float = 0.0
        self.enqueue_at: float = 2.0
        self.is_done = False
        self.is_staggered = True
        self.recording_mode = False
        self.window_size: T.Tuple[int, int] = pygame.display.get_window_size()
        self.mouse_pos: T.Tuple[int, int] = pygame.mouse.get_pos()
        self.keys: T.Dict[int, KeySquare] = {}
        self.last_update: T.Optional[float] = None
        
        self.window_active = True
        self.window_focused = True
        self.macro = InterceptionSender()
        self.known_files: T.Dict[str, str] = discover_files()
        out_port = pygame.midi.get_default_output_id()
        in_port = pygame.midi.get_default_input_id()
        self.in_sounds: T.Optional[pygame.midi.Input] = None
        if in_port != -1:
            self.in_sounds = pygame.midi.Input(in_port)
            print("Now listening to", pygame.midi.get_device_info(in_port))
        self.out_sounds = pygame.midi.Output(out_port, 0)

        self.font = pygame.font.Font(pygame.font.get_default_font(), 32)
        
        if self.paused:
            pygame.display.set_caption("PAUSED")
        else:
            pygame.display.set_caption("PLAYING")

        self._setup_keys()

    def __getattr__(self, attrname) -> T.Any:
        try:
            return super().__getattr__(attrname)
        except AttributeError:
            return getattr(self.settings, attrname)
    
    def __setattr__(self, attrname, attrval) -> T.Any:
        if attrname != "settings" and attrname in dir(self.settings):
            return setattr(self.settings, attrname, attrval)
        else:
            return super().__setattr__(attrname, attrval)

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
                    xpos = center_xs[(real_col * N_PLAYABLE_OCTAVES) + (2 - row)]
                    ypos = center_ys[row]
                    if pitch not in self.keys:
                        self.keys[pitch] = KeySquare(
                            self,
                            pitch,
                            xpos,
                            ypos,
                        )
                    else:
                        self.keys[pitch].norm_xpos = xpos
                        self.keys[pitch].norm_ypos = ypos
                    real_col += 1
                pitch += 1
        self.is_staggered = True
    
    def dump(self) -> T.List[T.Tuple[int, float]]:
        full_dump: T.List[T.Tuple[int, float]] = []
        for k_id in self.keys:
            full_dump.extend(self.keys[k_id].dump())
        return full_dump

    def save(self) -> None:
        dump_midi_file(self.dump())

    def reviewing_recording(self) -> bool:
        if not self.recording_mode:
            return False
        else:
            for k_id in self.keys:
                if self.keys[k_id].when_ix != len(self.keys[k_id].when):
                    return True
            return False

    def _rearrange(self):
        left_norm = 0.10
        right_norm = 0.90
        bottom_norm = 0.85
        center_xs = np.linspace(left_norm, right_norm, N_PLAYABLE_OCTAVES * N_NOTES_PER_ROW, endpoint=True)

        for k_id, cx in zip(sorted(self.keys.keys()), center_xs):
            self.keys[k_id].norm_ypos = bottom_norm
            self.keys[k_id].norm_xpos = cx
        self.is_staggered = False

    def _transform_pitch(self, pitch: int) -> int:
        transposed = self.transpose_amount + pitch
        if self.keep_in_bounds:
            while transposed > HIGHEST_NOTE:
                transposed -= OCTAVE_SEMITONES
            while transposed < LOWEST_NOTE:
                transposed += OCTAVE_SEMITONES
        return transposed

    def enqueue_file(self, name: str, clear_existing: bool = False, min_confidence: float = 0.96):
        # Throw error is OK
        fn = self.known_files[name]
        self.now = 0
        notes = read_midi_file(fn)
        tr, tr_score = autotranspose(notes)
        if tr_score < min_confidence:
            print(f"Too many black notes: {name}: {int(tr_score*100)}% white")
            return
        print(f"automatically transposing by {tr}")
        tr_diff = tr - self.transpose_amount

        if clear_existing:
            for k_id in self.keys:
                self.keys[k_id].when.clear()
                self.keys[k_id].real_up()
            self.enqueue_at = 2.0

        
        sorted_ww = sorted(notes, key=lambda ww: ww[1], reverse=False)
        
        ngood = 0
        nbad = 0
        offset = self.enqueue_at
        for (what, when) in sorted_ww:
            what = self._transform_pitch(what + tr_diff)
            when = when + offset
            the_key = self.keys.get(what, None)
            if the_key is not None:
                the_key.when.append(when)
                ngood += 1
            else:
                nbad += 1
            self.enqueue_at = max(self.enqueue_at, when)
        print(f"{name}: {ngood} / {ngood + nbad} :: {int(ngood / (ngood+nbad) * 100)}%")


    def okay_to_progress(self) -> bool:
        if self.recording_plays:
            return True
        else:
            for k_id in self.keys:
                if not self.keys[k_id].okay_to_progress():
                    return False
            
            return True

    def update(self):
        nowtime = time.time()

        if self.last_update is not None:
            elapsed = nowtime - self.last_update
            if not self.paused and (not self.progression_mode or self.okay_to_progress()):
                self.now = self.now + (elapsed * self.timescale)

        self.last_update = nowtime

        self.window_size = pygame.display.get_window_size()
        self.mouse_pos = pygame.mouse.get_pos()
        self.window_active = pygame.display.get_active()
        self.window_focused = pygame.key.get_focused()
        
        prev_play = None
        for ev in pygame.event.get():
            if ev.type == pygame.WINDOWCLOSE:
                self.is_done = True
                break

            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    self.is_done = True
                    break
            
                if ev.key == pygame.K_0:
                    if self.recording_mode:
                        self.is_done = True
                        self.save()
                        break
                    else:
                        self.recording_mode = True
                        self.now = 0.0
                        self.timescale = 1.0
            
                if ev.key == pygame.K_RIGHT:
                    self.now += 15
                    prev_play = self.play_sounds
                    self.play_sounds = False
            
                if ev.key == pygame.K_LEFT:
                    self.now = max(0, self.now - 15)
                    prev_play = self.play_sounds
                    self.play_sounds = False
                    for k_id in self.keys:
                        self.keys[k_id].backout_before(self.now)
                
                if ev.key == pygame.K_UP:
                    self.timescale += 0.1
            
                if ev.key == pygame.K_DOWN:
                    self.timescale -= 0.1
                    self.timescale = max(0.1, self.timescale)
            
                if ev.key == pygame.K_1:
                    self.paused = not self.paused
                    if self.paused:
                        pygame.display.set_caption("PAUSED")
                    else:
                        pygame.display.set_caption("PLAYING")
                
                if ev.key == pygame.K_2:
                    if self.is_staggered:
                        self._rearrange()
                    else:
                        self._setup_keys()

                if ev.key == pygame.K_3:
                    self.progression_mode = not self.progression_mode
                
                if ev.key == pygame.K_p:
                    self.paused = not self.paused
            
                if not self.ignore_keypresses:
                    for k_id in self.keys:
                        k = self.keys[k_id]
                        if k.keyboard_key == ev.key:
                            k.real_down(was_keypress=True)
            
            elif ev.type == pygame.KEYUP:
                if not self.ignore_keypresses:
                    for k_id in self.keys:
                        k = self.keys[k_id]
                        if k.keyboard_key == ev.key:
                            k.real_up(was_keypress=True)
                
                if ev.key == pygame.K_p:
                    self.paused = not self.paused
            
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

        if prev_play is not None:
            self.play_sounds = prev_play

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
        if MAKE_TRANSPARENT:
            display.fill(TRANSPARENT_BACKGROUND)
        else:
            display.fill((230, 230, 230))
        for k_id in self.keys:
            key = self.keys[k_id]
            key.draw(self.now)
        pygame.display.flip()

    def start(self):
        self.now = 0.0
        if self.macro_output:
            self.macro.start()
        while True:
            self.update()
            
            if self.is_done:
                break

            self.draw()

            nowtime = time.time() - self.last_update
            time.sleep(0.01)
        if self.macro_output:
            self.macro.close()


def main():
    pygame.display.set_mode((800, 480), pygame.RESIZABLE)
    if MAKE_TRANSPARENT:
        make_window_transparent()
    game = MIDIRenderer()
    game.enqueue_file("recording_1", min_confidence=0)
    #for each_song in game.known_files:
    #    game.enqueue_file(each_song)
    game.start()


if __name__ == "__main__":
    main()