from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from chinese_calendar import is_holiday
from hyperot.events import *
from typing_extensions import override

import ModuleClass

BEIJING_TZ = ZoneInfo("Asia/Shanghai")
PEAK_PERIODS: tuple[tuple[time, time], ...] = (
    (time(9, 0), time(12, 0)),
    (time(14, 0), time(18, 0)),
)


@ModuleClass.ModuleRegister.register(GroupMessageEvent)
class Module(ModuleClass.Module[GroupMessageEvent]):
    @override
    @staticmethod
    def info() -> ModuleClass.ModuleInfo:
        return ModuleClass.ModuleInfo(
            is_hidden=False,
            module_name="DSMon",
            desc="展示 DeepSeek 工作日峰谷定价时段（排除法定节假日）",
            helps="发送“梁文”或 .ds 即可",
        )

    @staticmethod
    def is_statutory_holiday(day: date) -> bool:
        """中国法定节假日判断；节假日数据未覆盖该年份时回退为普通工作日规则。"""
        try:
            return is_holiday(day)
        except NotImplementedError:
            return False

    @staticmethod
    def is_peak_at(moment: datetime) -> bool:
        if moment.weekday() >= 5 or Module.is_statutory_holiday(moment.date()):
            return False
        current_time = moment.time()
        return any(start <= current_time < end for start, end in PEAK_PERIODS)

    def is_peak(self) -> bool:
        return self.is_peak_at(datetime.now(BEIJING_TZ))

    @staticmethod
    def get_next_peak_start(now: datetime) -> datetime:
        for days_ahead in range(370):
            candidate_date = now.date() + timedelta(days=days_ahead)
            if candidate_date.weekday() >= 5 or Module.is_statutory_holiday(candidate_date):
                continue
            for start, _ in PEAK_PERIODS:
                candidate = datetime.combine(candidate_date, start).replace(tzinfo=now.tzinfo)
                if candidate > now:
                    return candidate
        raise RuntimeError("无法计算下一个 DeepSeek 高峰时段")

    @staticmethod
    def format_duration(delta: timedelta) -> str:
        total_minutes = max(0, int(delta.total_seconds() // 60))
        days, remaining_minutes = divmod(total_minutes, 24 * 60)
        hours, minutes = divmod(remaining_minutes, 60)

        parts: list[str] = []
        if days > 0:
            parts.append(f"{days}天")
        if hours > 0 or days > 0:
            parts.append(f"{hours}小时")
        if minutes > 0 or not parts:
            parts.append(f"{minutes}分钟")
        return "".join(parts)

    def get_remaining_time_str(self) -> str:
        """
        返回当前时段剩余时间描述。
        峰时：显示距离峰时结束的剩余时间。
        谷时：显示距离下一个峰时开始的剩余时间。
        """
        now = datetime.now(BEIJING_TZ)
        current_time = now.time()
        today = now.date()

        if self.is_peak():
            end_time = next(end for start, end in PEAK_PERIODS if start <= current_time < end)
            end_dt = datetime.combine(today, end_time).replace(tzinfo=now.tzinfo)
            return f"剩余{self.format_duration(end_dt - now)}"

        next_start_dt = self.get_next_peak_start(now)
        return f"距下峰还有{self.format_duration(next_start_dt - now)}"

    def build_msg(self) -> str:
        status = "峰，小心钱包" if self.is_peak() else "谷，放心蹬"
        return f"现在是梁文{status}（{self.get_remaining_time_str()}）"

    @override
    async def handle(self):
        if str(self.event.message) == "梁文" or str(self.event.message) == ".ds":
            await self.actions.send_msg(
                user_id=self.event.user_id, group_id=self.event.group_id, message=self.build_msg()
            )
