from Hyper.ModuleClass import *

record: [str, dict[str, int]] = {}


@ModuleRegister.register(["message"])
class Repeat(Module):
    async def handle(self):
        if record.get(self.event.group_id) is None:
            record[self.event.group_id] = {}
            record[self.event.group_id][str(await self.event.message.get())] = 1
        else:
            if record[self.event.group_id].get(str(await self.event.message.get())) is not None:
                record[self.event.group_id][str(await self.event.message.get())] += 1
                if record[self.event.group_id][str(await self.event.message.get())] >= 3:
                    record[self.event.group_id][str(await self.event.message.get())] = 0
                    await self.actions.send(group_id=self.event.group_id, message=self.event.message)
            else:
                record[self.event.group_id][str(await self.event.message.get())] = 1
