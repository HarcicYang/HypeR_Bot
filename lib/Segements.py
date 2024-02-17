class Text:
    def __init__(self, text: str):
        self.content = {"type": "text", "data": {"text": text}}

    def set(self, text: str) -> None:
        self.content["data"]["text"] = text

    def get(self) -> str:
        return self.content["data"]["text"]

    def get_raw(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return self.content["data"]["text"]

    def __repr__(self) -> str:
        return str(self.content)


class Image:
    def __init__(self, image: str):
        self.content = {"type": "image", "data": {"file": image}}

    def set(self, text: str) -> None:
        self.content["data"]["text"] = text

    def get(self) -> str:
        return self.content["data"]["file"]

    def get_raw(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return "[图片]"

    def __repr__(self) -> str:
        return str(self.content)


class At:
    def __init__(self, user_id: str):
        self.content = {"type": "at", "data": {"qq": user_id}}

    def set(self, user_id: str) -> None:
        self.content["data"]["qq"] = user_id

    def get(self) -> str:
        return self.content["data"]["qq"]

    def get_raw(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return f"@{self.content['data']['qq']} "

    def __repr__(self) -> str:
        return str(self.content)


class Reply:
    def __init__(self, message_id: str):
        self.content = {"type": "reply", "data": {"id": message_id}}

    def set(self, message_id: str) -> None:
        self.content["data"]["id"] = message_id

    def get(self) -> str:
        return self.content["data"]["id"]

    def get_raw(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return f"[回复{self.content['data']['id']}]"

    def __repr__(self) -> str:
        return str(self.content)


class Face:
    def __init__(self, face_id: str):
        self.content = {"type": "face", "data": {"id": face_id}}

    def set(self, face_id: str) -> None:
        self.content["data"]["id"] = face_id

    def get(self) -> str:
        return self.content["data"]["id"]

    def get_raw(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return f"[表情{self.content['data']['id']}]"

    def __repr__(self) -> str:
        return str(self.content)


class Location:
    def __init__(self, lat: str, lon: str):
        self.content = {"type": "location", "data": {"lat": lat, "lon": lon}}

    def set(self, lat: str, lon: str) -> None:
        self.content["data"]["lat"] = lat
        self.content["data"]["lon"] = lon

    def get(self) -> tuple[str, str]:
        return self.content["data"]["lat"], self.content["data"]["lon"]

    def get_raw(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return f"[位置{self.content['data']['lat']}, {self.content['data']['lon']}]"

    def __repr__(self) -> str:
        return str(self.content)
