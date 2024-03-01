from lib import Manager, Listener, Segments


class ModuleClass:
    def __init__(self, actions: Listener.Actions, event: Manager.Event):
        self.actions = actions
        self.event = event

    async def handle(self):
        try:
            cmds = str(self.event.message)
        except AttributeError:
            return

        if cmds.startswith(f"@{self.event.self_id}"):
            if "先吃饭吧" in cmds:
                self.actions.send(group_id=self.event.group_id,
                                  message=Manager.Message([Segments.Text("好啊好啊，不过，饭还没做好")]))
            elif "先洗澡吧" in cmds:
                self.actions.send(group_id=self.event.group_id,
                                  message=Manager.Message([Segments.Text("好啊好啊，不过，水还没烧好")]))
            elif "嘿嘿我来了" in cmds:
                self.actions.send(group_id=self.event.group_id,
                                  message=Manager.Message([Segments.Text("啊啊啊，什么啊，群友好恐怖呜呜呜")]))
            else:
                message = Manager.Message(
                    [Segments.Text("主人会选择哪个套餐呢。。。"), Segments.KeyBoard(
                        {
                            "rows": [{
                                "buttons": [{
                                    "id": "1",
                                    "render_data": {
                                        "label": "先吃饭！",
                                        "visited_label": "先吃饭！",
                                        "style": 1
                                    },
                                    "action": {
                                        "type": 2,
                                        "permission": {
                                            "type": 2
                                        },
                                        "enter": True,
                                        "click_limit": 10,
                                        "unsupport_tips": "Harcic",
                                        "data": "先吃饭吧"
                                    }
                                },
                                    {
                                        "id": "2",
                                        "render_data": {
                                            "label": "先洗澡！",
                                            "visited_label": "先洗澡！",
                                            "style": 1
                                        },
                                        "action": {
                                            "type": 2,
                                            "permission": {
                                                "type": 2
                                            },
                                            "enter": True,
                                            "click_limit": 10,
                                            "unsupport_tips": "Harcic",
                                            "data": "先洗澡吧"
                                        }
                                    },
                                    {
                                        "id": "3",
                                        "render_data": {
                                            "label": "先吃我？",
                                            "visited_label": "先吃我？",
                                            "style": 1
                                        },
                                        "action": {
                                            "type": 2,
                                            "permission": {
                                                "type": 2
                                            },
                                            "enter": True,
                                            "click_limit": 10,
                                            "unsupport_tips": "Harcic",
                                            "data": "嘿嘿我来了小机器人！！"
                                        }
                                    }
                                ]
                            }],
                            "bot_appid": 0
                        }
                    )
                     ])
                self.actions.send(group_id=self.event.group_id, message=message)

