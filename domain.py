from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True, eq=False)
class FileInfo:
    file_name: str
    size: int
    url: str = ''
    local_path: str = ''


@dataclass(init=True, slots=True, repr=False)
class Echo360Lecture:
    date: datetime | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    course_name: str = ''
    title: str = ''
    url: str = ''
    week_number: int = 0
    lecture_in_week: int = 0
    file_infos: list[FileInfo] = field(default_factory=list)

    @property
    def lecture_identifier(self) -> str:
        return f'{self.week_number}.{self.lecture_in_week}'

    def __repr__(self) -> str:
        return f'[{self.date:%d.%m.%Y} - {self.start_time:%H:%M}-{self.end_time:%H:%M}] {self.title}'
