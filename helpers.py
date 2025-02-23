import os
import sys


def get_long_path(path: str) -> str:
    if sys.platform == 'win32' and not path.startswith('\\\\?\\'):
        return f'\\\\?\\{os.path.abspath(path)}'
    return os.path.abspath(path)


def get_file_size_string(size: int) -> str:
    if size >= 1 << 30:
        return f'{size / (1 << 30):.2f} GiB'
    else:
        return f'{size / (1 << 20):.2f} MiB'
