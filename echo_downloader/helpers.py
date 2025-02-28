import sys
from pathlib import Path

_SAFE_CHARS = frozenset('ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                        'abcdefghijklmnopqrstuvwxyz'
                        '0123456789'
                        '_.-~'
                        ' #[]õäöüÕÄÖÜ')


def encode_path(s: str) -> str:
    return ''.join(f'%{ord(c):02X}' if c not in _SAFE_CHARS else c for c in s)


def get_long_path(path: Path) -> Path:
    if sys.platform == 'win32' and not str(path).startswith('\\\\?\\'):
        return Path(f'\\\\?\\{path.resolve()}')
    return path.resolve()


def get_file_size_string(size: int) -> str:
    if size >= 1 << 30:
        return f'{size / (1 << 30):.2f} GiB'
    else:
        return f'{size / (1 << 20):.2f} MiB'
