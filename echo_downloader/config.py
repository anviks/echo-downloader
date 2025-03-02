from pathlib import Path

import platformdirs
import yaml
from objectify import dict_to_object


class EchoDownloaderConfig:
    max_logs: int
    path_completion: bool
    delete_source_files: bool
    title_suffixes: dict[str, str]


def load_config() -> EchoDownloaderConfig:
    default_config_path = Path(__file__).parent / 'config.yaml'
    config_dir = platformdirs.user_config_path('EchoDownloader', appauthor=False, roaming=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    custom_config_path = config_dir / 'config.yaml'

    with open(default_config_path) as f:
        file_contents = f.read()

    config_dict = yaml.safe_load(file_contents)

    if not custom_config_path.exists():
        with open(custom_config_path, 'w') as f:
            f.write(file_contents)
    else:
        with open(custom_config_path, 'r') as f:
            config_dict.update(yaml.safe_load(f))

    return dict_to_object(config_dict, EchoDownloaderConfig)
