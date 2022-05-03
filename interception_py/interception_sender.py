from .interception import *
from .consts import *
from .scancode import ScanCode
import time
import os
import json
from contextlib import contextmanager


class InterceptionSender():
    def __init__(self):
        pass

    def start(self):
        self.c = interception()
        self.calibrate()
    
    def calibrate(self):
        self.c.set_filter(interception.is_keyboard, interception_filter_key_state.INTERCEPTION_FILTER_KEY_DOWN.value)
        self.device = self.c.wait()
        self.sample_down = self.c.receive(self.device)
        self.c.send(self.device, self.sample_down)

        self.c.set_filter(interception.is_keyboard, interception_filter_key_state.INTERCEPTION_FILTER_KEY_UP.value)
        while True:
            device = self.c.wait()
            event = self.c.receive(device)
            self.c.send(device, event)
            if device == self.device:
                self.sample_up = event
                break
        self.c.set_filter(interception.is_keyboard, interception_filter_key_state.INTERCEPTION_FILTER_KEY_NONE.value)
        print(f"Got device {self.device}, DOWN event: {self.sample_down}, and UP event: {self.sample_up}")

    def _keyDown(self, scancode: int):
        self.sample_down.code = scancode
        self.c.send(self.device, self.sample_down)
    
    def _keyUp(self, scancode: int):
        self.sample_up.code = scancode
        self.c.send(self.device, self.sample_up)

    def press(self, keys, presses=1, interval=0.0):
        if type(keys) == str:
            if len(keys) > 1:
                keys = keys.lower()
            keys = [keys] # If keys is 'enter', convert it to ['enter'].
        else:
            lowerKeys = []
            for s in keys:
                if len(s) > 1:
                    lowerKeys.append(s.lower())
                else:
                    lowerKeys.append(s)
            keys = lowerKeys
        interval = float(interval)
        for i in range(presses):
            for k in keys:
                self._keyDown(ScanCode.get(k))
                self._keyUp(ScanCode.get(k))
            time.sleep(interval)

    def hold(self, keys):
        """Context manager that performs a keyboard key press down upon entry,
        followed by a release upon exit.

        Args:
        key (str, list): The key to be pressed. The valid names are listed in
        KEYBOARD_KEYS. Can also be a list of such strings.
        Returns:
        None
        """
        if type(keys) == str:
            if len(keys) > 1:
                keys = keys.lower()
            keys = [keys] # If keys is 'enter', convert it to ['enter'].
        else:
            lowerKeys = []
            for s in keys:
                if len(s) > 1:
                    lowerKeys.append(s.lower())
                else:
                    lowerKeys.append(s)
            keys = lowerKeys
        for k in keys:
            self._keyDown(ScanCode.get(k))
        try:
            yield
        finally:
            for k in keys:
                self._keyUp(ScanCode.get(k))

    def isValidKey(self, key):
        """Returns a Boolean value if the given key is a valid value

        Args:
        key (str): The key value.

        Returns:
        bool: True if key is a valid value, False if not.
        """
        return ScanCode.valid(key)

    def keyDown(self, key):
        """Performs a keyboard key press without the release. This will put that
        key in a held down state.

        Args:
        key (str): The key to be pressed down. The valid names are listed in
        KEYBOARD_KEYS.

        Returns:
        None
        """
        if len(key) > 1:
            key = key.lower()

        self._keyDown(ScanCode.get(key))

    def keyUp(self, key):
        """Performs a keyboard key release (without the press down beforehand).

        Args:
        key (str): The key to be released up. The valid names are listed in
        KEYBOARD_KEYS.

        Returns:
        None
        """
        if len(key) > 1:
            key = key.lower()

        self._keyUp(ScanCode.get(key))

    def typewrite(self, message, interval=0.0):
        """Performs a keyboard key press down, followed by a release, for each of
        the characters in message.

        The message argument can also be list of strings, in which case any valid
        keyboard name can be used.

        Since this performs a sequence of keyboard presses and does not hold down
        keys, it cannot be used to perform keyboard shortcuts. Use the hotkey()
        function for that.

        Args:
            message (str, list): If a string, then the characters to be pressed. If a
            list, then the key names of the keys to press in order. The valid names
            are listed in KEYBOARD_KEYS.
            interval (float, optional): The number of seconds in between each press.
            0.0 by default, for no pause in between presses.

        Returns:
            None
        """
        interval = float(interval)

        for c in message:
            if len(c) > 1:
                c = c.lower()
            self.press(c)
            time.sleep(interval)

    def hotkey(self, *args, **kwargs):
        """Performs key down presses on the arguments passed in order, then performs
        key releases in reverse order.

        The effect is that calling hotkey('ctrl', 'shift', 'c') would perform a
        "Ctrl-Shift-C" hotkey/keyboard shortcut press.

        Args:
        key(s) (str): The series of keys to press, in order. This can also be a
            list of key strings to press.
        interval (float, optional): The number of seconds in between each press.
            0.0 by default, for no pause in between presses.

        Returns:
        None
        """
        interval = float(kwargs.get("interval", 0.0))  # TODO - this should be taken out.

        for c in args:
            if len(c) > 1:
                c = c.lower()
            self._keyDown(ScanCode.get(c))
            time.sleep(interval)
        for c in reversed(args):
            if len(c) > 1:
                c = c.lower()
            self._keyUp(ScanCode.get(c))
            time.sleep(interval)

    def close(self):
        self.c._destroy_context()
    
    def __enter__(self, *args):
        self.start()
        return self
    
    def __exit__(self, *args):
        self.close()


if __name__ == "__main__":
    with InterceptionSender() as sender:
        time.sleep(5)
        sender.typewrite('z')
        sender.close()
