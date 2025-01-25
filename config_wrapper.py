from typing import Literal, get_args

from selenium.webdriver.common.by import By

type LocatorStrategies = Literal[
    'id', 'xpath', 'link text', 'partial link text', 'name', 'tag name', 'class name', 'css selector']
type Locator = tuple[LocatorStrategies, str]

by_values = tuple(v for k, v in dict(By.__dict__).items() if not k.startswith('_'))

assert get_args(LocatorStrategies.__value__) == by_values


class EchoDownloaderConfig:
    locators: 'Locators'
    attributes: 'Attributes'
    formats: 'Formats'
    logging: 'Logging'
    conversion_table: dict[str, dict[int, str]]
    file_pairs: dict[str, list[tuple[str, str]]]
    course_urls: dict[str, str]
    searched_files: dict[str, tuple[str, ...]]
    course_abbreviations: dict[str, str]

    class Locators:
        course_name: Locator
        lectures: Locator
        lecture_date: Locator
        lecture_time: Locator

    class Attributes:
        lecture_id_attribute: str

    class Formats:
        lecture_url: str
        date_format: str
        time_format: str

    class Logging:
        level: Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        format: str
        datefmt: str
