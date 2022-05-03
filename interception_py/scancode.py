import os
import json

import typing as T

SCANCODE_JSON_PATH = os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "scancodes_lookup.json")

class ScanCode:
    _lookup: T.Optional[T.Dict[str, int]] = None

    @classmethod
    def _load_cached(cls):
        if cls._lookup is None:
            with open(SCANCODE_JSON_PATH) as f:
                cls._lookup = json.load(f)
    
    @classmethod
    def get(cls, item: str):
        cls._load_cached()
        return T.cast(T.Dict[str, int], cls._lookup)[item]
    
    @classmethod
    def all(cls):
        cls._load_cached()
        return sorted(cls._lookup.keys(), key=lambda s: (0 if len(s) == 1 else 2 if s[0] in 'LR' else 1, s[1:] if s[0] in 'LR' else s))
    
    @classmethod
    def valid(cls, item):
        cls._load_cached()
        return item in cls._lookup


