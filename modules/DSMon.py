from datetime import datetime, time, timedelta
from hyperot.events import *
from typing_extensions import override

import ModuleClass


@ModuleClass.ModuleRegister.register(GroupMessageEvent)
class Module(ModuleClass.Module[GroupMessageEvent]):
    @override
    @staticmethod
    def info() -> ModuleClass.ModuleInfo:
        return ModuleClass.ModuleInfo(
            is_hidden=False,
            module_name="DSMon",
            desc="展示 DeepSeek 定价时段",
            helps="发送“梁文”或 .ds 即可",
        )

    def is_peak(self) -> bool:
        return time(9, 0) <= datetime.now().time() <= time(12, 0) or time(14, 0) <= datetime.now().time() <= time(18, 0)

    def get_remaining_time_str(self) -> str:
        """
        返回当前时段剩余时间描述。
        峰时：显示距离峰时结束的剩余时间。
        谷时：显示距离下一个峰时开始的剩余时间。
        """
        now = datetime.now()
        current_time = now.time()
        today = now.date()

        peak1_start = time(9, 0)
        peak1_end = time(12, 0)
        peak2_start = time(14, 0)
        peak2_end = time(18, 0)

        if self.is_peak():
            # 判断是上午峰时还是下午峰时
            if peak1_start <= current_time <= peak1_end:
                end_dt = datetime.combine(today, peak1_end)
            else:  # 下午峰时
                end_dt = datetime.combine(today, peak2_end)
            delta = end_dt - now
            if delta.total_seconds() <= 0:
                return "剩余0分钟"
            total_minutes = int(delta.total_seconds() // 60)
            hours, minutes = divmod(total_minutes, 60)
            return f"剩余{hours}小时{minutes}分钟" if hours > 0 else f"剩余{minutes}分钟"
        else:
            # 谷时：判断下一个峰时开始时间
            if peak1_end < current_time < peak2_start:
                # 12:00 之后，14:00 之前
                next_start_dt = datetime.combine(today, peak2_start)
            else:
                # 18:00 之后，或 0:00 - 9:00 之前
                next_start_dt = datetime.combine(today + timedelta(days=1), peak1_start)
            delta = next_start_dt - now
            total_minutes = int(delta.total_seconds() // 60)
            hours, minutes = divmod(total_minutes, 60)
            return f"距下峰还有{hours}小时{minutes}分钟" if hours > 0 else f"距下峰还有{minutes}分钟"

    def build_msg(self) -> str:
        status = "峰，小心钱包" if self.is_peak() else "谷，放心蹬"
        return f"现在是梁文{status}（{self.get_remaining_time_str()}）"

    @override
    async def handle(self):
        if "梁文" in str(self.event.message).replace("梁文锋", "") or str(self.event.message) == ".ds":
            await self.actions.send_msg(
                user_id=self.event.user_id,
                group_id=self.event.group_id,
                message=self.build_msg()
            )