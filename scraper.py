import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime as dt
from types import TracebackType
from typing import Any, Self
from urllib.parse import urlparse

from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.wait import WebDriverWait

from config_wrapper import EchoDownloaderConfig
from domain import Echo360Lecture, FileInfo

logger = logging.getLogger(__name__)


class EchoScraper:
    def __init__(self,
                 configuration: EchoDownloaderConfig,
                 url: str,
                 *,
                 headless: bool = True):
        self.config = configuration
        self.url = url
        self.headless = headless

        self.lectures: list[Echo360Lecture] = []
        self.__driver: WebDriver | None = None
        # self.course_url = self.config.course_urls[self.course_title]
        # self.searched_files = self.config.searched_files[self.course_title]

    @property
    def driver(self) -> WebDriver:
        if self.__driver is None:
            raise RuntimeError(f"{self.__class__.__name__} must be used within a context manager to use the driver.")
        return self.__driver

    def get_lecture_selection(self):
        course_name = self.get_course_name()
        self.driver.get(self.url)
        elements_of_lectures: list[WebElement] = (WebDriverWait(self.driver, 10).until(ec.presence_of_all_elements_located(self.config.locators.lectures)))
        selection = []
        lectures = []
        for element in elements_of_lectures:
            lecture = Echo360Lecture()
            lecture.course_name = course_name

            date_string = element.find_element(*self.config.locators.lecture_date).text
            lecture.date = dt.strptime(date_string, self.config.formats.date_format)

            start_time_string, end_time_string = element.find_element(*self.config.locators.lecture_time).text.split(
                '-')
            lecture.start_time = dt.strptime(start_time_string, self.config.formats.time_format)
            lecture.end_time = dt.strptime(end_time_string, self.config.formats.time_format)

            lecture_id = element.get_attribute(self.config.attributes.lecture_id_attribute)
            lecture.url = self.config.formats.lecture_url.format(lecture_id=lecture_id)

            lecture.title = element.find_element(By.CLASS_NAME, 'title').text

            lectures.append(lecture)

        self.assign_numbers(lectures)

        for lecture in lectures:
            lecture.file_infos = self.get_lecture_files(lecture.url)
            # October 22, 2024 14:00-15:29 | ICO-2024-SP-ICD0011 - Veebirakendused Java baasil
            selection.append((lecture, f'{lecture.date.strftime("%B %d, %Y")} {lecture.start_time.strftime("%H:%M")}-{lecture.end_time.strftime("%H:%M")} | {lecture.title}'))

        return selection

    def scrape_all_lectures(self) -> None:
        logger.info('Collecting lecture URLs...')
        self.driver.get(self.url)
        self.get_all_lecture_urls()
        self.assign_numbers(self.lectures)

        logger.info('Collecting lecture file URLs...')
        for lecture in self.lectures:
            logger.info(f'Collecting file URLs for {lecture!r}')
            lecture.file_infos = self.get_lecture_files(lecture.url)

    @staticmethod
    def assign_numbers(lectures: list[Echo360Lecture]) -> None:
        earliest_date = min(lecture.date for lecture in lectures)
        grouped_by_weeks: defaultdict[int, list[Echo360Lecture]] = defaultdict(list)

        for lecture in lectures:
            lecture.week_number = ((lecture.date - earliest_date).days // 7) + 1
            grouped_by_weeks[lecture.week_number].append(lecture)

        for groups in grouped_by_weeks.values():
            for i, lecture in enumerate(groups, 1):
                lecture.lecture_in_week = i


    def get_all_lecture_urls(self) -> None:
        course_name = self.get_course_name()
        self.driver.get(self.url)
        elements_of_lectures: list[WebElement] = (WebDriverWait(self.driver, 10)
        .until(
            ec.presence_of_all_elements_located(self.config.locators.lectures)))

        for element in elements_of_lectures:
            lecture = Echo360Lecture()
            lecture.course_name = course_name

            date_string = element.find_element(*self.config.locators.lecture_date).text
            start_time_string, end_time_string = element.find_element(*self.config.locators.lecture_time).text.split('-')

            lecture.date = dt.strptime(date_string, self.config.formats.date_format)
            lecture.start_time = dt.strptime(start_time_string, self.config.formats.time_format)
            lecture.end_time = dt.strptime(end_time_string, self.config.formats.time_format)

            lecture_id = element.get_attribute(self.config.attributes.lecture_id_attribute)
            lecture.url = self.config.formats.lecture_url.format(lecture_id=lecture_id)

            self.lectures.append(lecture)

    def get_lecture_files(self, lecture_url: str, timeout_seconds: int = 4) -> list[FileInfo]:
        self.driver.get(lecture_url)
        self.driver.get_log('performance')
        lecture_file_infos: dict[str, FileInfo] = {}
        start_time = time.time()

        while True:
            if time.time() - start_time > timeout_seconds:
                break

            for entry in self.driver.get_log('performance'):
                message = self.get_message_attribute(entry)

                if message['method'] != 'Network.responseReceived':
                    continue

                response_url = message['params']['response']['url']
                response_file_name = os.path.basename(urlparse(response_url).path)

                if response_file_name in ["s0q1.m4s", "s1q1.m4s", "s2q1.m4s"]:  # TODO: Remove hardcoded filenames
                    file_size = message['params']['response']['headers']['Content-Range'].split('/')[1]
                    lecture_file_infos.setdefault(response_file_name, FileInfo(response_file_name, int(file_size), response_url))

                if len(lecture_file_infos) == len(["s0q1.m4s", "s1q1.m4s", "s2q1.m4s"]):  # TODO: Remove hardcoded filenames
                    break
            else:
                continue
            break

        return list(lecture_file_infos.values())

    def get_course_name(self) -> str:
        self.driver.get(self.url)
        heading_element: WebElement = (WebDriverWait(self.driver, 10)
                                       .until(ec.presence_of_element_located(self.config.locators.course_name)))
        course_name: str = self.driver.execute_script('return arguments[0].childNodes[2].textContent;',
                                                      heading_element).strip()

        return course_name

    def __enter__(self) -> Self:
        self.__setup_driver()
        return self

    def __exit__(self,
                 exc_type: type[BaseException] | None,
                 exc_val: BaseException | None,
                 exc_tb: TracebackType | None) -> None:
        self.driver.quit()
        self.__driver = None

    @staticmethod
    def get_message_attribute(entry: dict[str, Any]) -> dict[str, Any]:
        response: dict[str, Any] = json.loads(entry['message'])['message']
        return response

    def __setup_driver(self) -> None:
        options = Options()
        if self.headless:
            options.add_argument('--headless')

        options.add_argument('--log-level=3')
        options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

        self.__driver = WebDriver(options=options)
