import datetime


class Levels:
    def __init__(self):
        self.TRACE = f"✔️ \033[{47}m\033[{30}mTRACE \033[0m\033[0m "
        self.INFO = f"ℹ️ \033[{47}m\033[{30}mINFO \033[0m\033[0m "
        self.WARNING = f"⚠️ \033[{43}mWARN \033[0m "
        self.ERROR = f"❌ \033[{41}mERROR\033[0m "
        self.CRITICAL = f"🔴 \033[{41};{1}m*CRIT\033[0m "
        self.DEBUG = f"🛠️ \033[{43}mDEBUG\033[0m "

        self.level_nums = {
            self.TRACE: -1,
            self.INFO: 0,
            self.WARNING: 1,
            self.ERROR: 2,
            self.CRITICAL: 3,
            self.DEBUG: 10,
        }

        self.level_names = {
            "TRACE": self.TRACE,
            "INFO": self.INFO,
            "WARNING": self.WARNING,
            "ERROR": self.ERROR,
            "CRITICAL": self.CRITICAL,
            "DEBUG": self.DEBUG,
        }


levels = Levels()


class Logger:
    def __init__(self):
        self.log_level = levels.INFO

    def set_level(self, level: str):
        if level in levels.level_names:
            self.log_level = levels.level_names[level]
        else:
            self.log("未知的日志等级", levels.ERROR)

    def log(self, message: str, level: str = levels.INFO):
        if levels.level_nums[level] < levels.level_nums[self.log_level]:
            return None
        time = datetime.datetime.now()
        content = f" \033[38;5;244m[{str(time)[:-4]}]\033[0m {level} {message}"
        print(content)
