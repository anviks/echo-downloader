from typing import Literal


class EchoDownloaderConfig:
    logging: 'Logging'
    title_suffixes: dict[str, str]

    class Logging:
        level: Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        format: str
        datefmt: str
