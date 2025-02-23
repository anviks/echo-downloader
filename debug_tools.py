import asyncio
from functools import wraps

import jsonpickle


class lecture_cache:
    @staticmethod
    def write(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)

            with open('test_lectures.json', 'w') as f:
                f.write(jsonpickle.encode(result, indent=2))

            return result

        return wrapper

    @staticmethod
    def read(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            with open('test_lectures.json', 'r') as f:
                result = jsonpickle.decode(f.read())

            await asyncio.sleep(1)
            return result

        return wrapper
