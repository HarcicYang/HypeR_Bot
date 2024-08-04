import json
import os
import shutil
import traceback

from Hyper import Logger


class Cacher:
    def __init__(self, cache_time: int = 5):
        self.cache_time: int = cache_time
        self.cached: dict = {}

    def cache(self, func):
        def wrapper(*args, **kwargs):
            if kwargs.get("no_cache", False):
                kwargs.pop("no_cache")
                return func(*args, **kwargs)
            if str(kwargs) not in self.cached:
                ret = func(*args, **kwargs)
                self.cached[str(kwargs)] = ret
                if len(self.cached) >= self.cache_time:
                    for i in self.cached:
                        del self.cached[i]
                        break
                return ret
            else:
                return self.cached[str(kwargs)]

        return wrapper

    def cache_async(self, func):
        async def wrapper(*args, **kwargs):
            if kwargs.get("no_cache", False):
                kwargs.pop("no_cache")
                return await func(*args, **kwargs)
            if str(kwargs) not in self.cached:
                ret = await func(*args, **kwargs)
                self.cached[str(kwargs)] = ret
                if len(self.cached) >= self.cache_time:
                    for i in self.cached:
                        del self.cached[i]
                        break
                return ret
            else:
                return self.cached[str(kwargs)]

        return wrapper


class ErrorHandler:
    def __init__(self, level=Logger.levels.ERROR, retries: int = 0):
        self.level = level
        self.logger = Logger.Logger()
        self.retries = retries

    def handle(self, func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except:
                self.logger.log(f"出现错误：\n{str(traceback.format_exc())}", level=self.level)

        return wrapper

    def handle_async(self, func):
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except:
                self.logger.log(f"出现错误：\n{str(traceback.format_exc())}", level=self.level)

        return wrapper

    def auto_retry(self, func):
        def wrapper(*args, **kwargs):
            retried = 0
            while retried < self.retries:
                retried += 1
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    self.logger.log(f"出现错误：\n{str(e)}, 正在重试...", level=self.level)
            self.logger.log(f"错误在{retried}次重试后失败", level=self.level)

        return wrapper

    def auto_retry_async(self, func):
        async def wrapper(*args, **kwargs):
            retried = 0
            while retried < self.retries:
                retried += 1
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    self.logger.log(f"出现错误：\n{str(e)}, 正在重试...", level=self.level)
            self.logger.log(f"错误在{retried}次重试后失败", level=self.level)

        return wrapper


class Random:
    def __init__(self, seed: int = None):
        self.seed = seed

    def random(self) -> int:
        self.seed = self.seed ** 2
        self.seed = int(str(self.seed)[:7])
        return int(str(self.seed)[1:5])

    def __call__(self) -> int:
        return self.random()


class FileManager:
    @staticmethod
    def create(path: str) -> bool:
        try:
            with open(path, "w") as f:
                f.write("")
        except (FileExistsError | OSError | IOError):
            return False

        return True

    @staticmethod
    def exists(path: str) -> bool:
        try:
            with open(path, "r") as f:
                f.read()
                return True
        except FileNotFoundError:
            return False

    @staticmethod
    @Cacher(7).cache
    def read_as_text(path: str, encoding: str = "utf-8") -> str:
        with open(path, "r", encoding=encoding) as f:
            return f.read()

    @staticmethod
    @Cacher(7).cache
    def read_as_json(path: str, encoding: str = "utf-8") -> dict | list:
        with open(path, "r", encoding=encoding) as f:
            return json.load(f)

    @staticmethod
    @Cacher(7).cache
    def read_raw(path: str) -> bytes:
        with open(path, "rb") as f:
            return f.read()

    @staticmethod
    def delete(path: str) -> bool:
        try:
            os.remove(path)
            return True
        except (FileNotFoundError | OSError | IOError):
            return False

    @staticmethod
    def copy(path1: str, path2: str) -> bool:
        try:
            shutil.copy(path1, path2)
            return True
        except (FileNotFoundError | OSError | IOError):
            return False
