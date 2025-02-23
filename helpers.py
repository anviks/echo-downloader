import sys
from pathlib import Path
from urllib.parse import quote

SAFE_CHARS = ' #[]'


def encode_path(s: str) -> str:
    return quote(s, safe=SAFE_CHARS)


def get_long_path(path: Path) -> Path:
    if sys.platform == 'win32' and not str(path).startswith('\\\\?\\'):
        return Path(f'\\\\?\\{path.resolve()}')
    return path.resolve()


def get_file_size_string(size: int) -> str:
    if size >= 1 << 30:
        return f'{size / (1 << 30):.2f} GiB'
    else:
        return f'{size / (1 << 20):.2f} MiB'
