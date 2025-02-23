from pathlib import Path
from typing import Literal

import platformdirs
import yaml
from objectify import dict_to_object


class EchoDownloaderConfig:
    logging: 'Logging'
    title_suffixes: dict[str, str]

    class Logging:
        level: Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        format: str
        datefmt: str


def load_config() -> EchoDownloaderConfig:
    default_config_path = Path(__file__).parent / 'config.yaml'
    config_dir = platformdirs.user_config_dir('echo-downloader', 'anviks', roaming=True)
    custom_config_path = Path(config_dir) / 'config.yaml'

    with open(default_config_path) as f:
        file_contents = f.read()

    config_dict = yaml.safe_load(file_contents)

    if not custom_config_path.exists():
        custom_config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(custom_config_path, 'w') as f:
            f.write(file_contents)
    else:
        with open(custom_config_path) as f:
            config_dict.update(yaml.safe_load(f))

    return dict_to_object(config_dict, EchoDownloaderConfig)