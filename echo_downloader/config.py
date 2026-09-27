from pathlib import Path

import platformdirs
import tomllib
from objectify import dict_to_object


class EchoDownloaderConfig:
    max_logs: int
    path_completion: bool
    delete_source_files: bool
    title_suffixes: dict[str, str]


def load_config() -> EchoDownloaderConfig:
    default_config_path = Path(__file__).parent / 'config.toml'
    config_dir = platformdirs.user_config_path('EchoDownloader', appauthor=False, roaming=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    custom_config_path = config_dir / 'config.toml'

    with open(default_config_path) as f:
        file_contents = f.read()

    config_dict = tomllib.loads(file_contents)

    if not custom_config_path.exists():
        with open(custom_config_path, 'w') as f:
            f.write(file_contents)
    else:
        with open(custom_config_path, 'rb') as f:
            config_dict.update(tomllib.load(f))

    return dict_to_object(config_dict, EchoDownloaderConfig)
