import httpx
import json
from httpx import Timeout
from dataclasses import dataclass
from typing import Iterator


@dataclass
class Response:
    thinking: str
    text: str


@dataclass(frozen=True)
class API:
    base_url: str
    api_version: int
    _chat_session_create: str
    _completion: str
    _fetch_history: str
    _delete_session: str

    @property
    def api_version_str(self) -> str:
        return str(f"api/v{self.api_version}")

    @property
    def chat_session_create(self) -> str:
        return str(f"https://{self.base_url}/{self.api_version_str}/{self._chat_session_create}")

    @property
    def completion(self) -> str:
        return str(f"https://{self.base_url}/{self.api_version_str}/{self._completion}")

    @property
    def fetch_history(self) -> str:
        return str(f"https://{self.base_url}/{self.api_version_str}/{self._fetch_history}")

    @property
    def delete_session(self) -> str:
        return str(f"https://{self.base_url}/{self.api_version_str}/{self._delete_session}")


class Session:
    api = API(
        "chat.deepseek.com",
        0,
        "chat_session/create",
        "chat/completion",
        "chat/history_messages",
        "chat_session/delete"
    )

    def __init__(self, session_id: str, auth: str, cookie: str, api: API = None):
        self.session_id = session_id
        self.auth = auth
        self.cookie = cookie
        if api:
            self.api = api
        else:
            pass

    def fetch_history(self) -> dict:
        response = httpx.get(
            self.api.fetch_history,
            params={"chat_session_id": self.session_id},
            headers={"authorization": self.auth}
        )
        return response.json()

    def get_code(self) -> int:
        return self.fetch_history()["data"]["biz_data"]["chat_session"]["current_message_id"]

    @classmethod
    def create(cls, auth: str, cookie: str, api: API = None) -> "Session":
        if not api:
            api = cls.api
        response = httpx.post(
            api.chat_session_create,
            headers={"authorization": auth},
            json={"character_id": None}
        )
        if response.json()["code"] != 0:
            raise Exception()
        ses = response.json()["data"]["biz_data"]["id"]
        return cls(ses, auth, cookie, api)

    def gen_completion(
            self, prompt: str, search: bool = False, thinking: bool = False, timeout: float = 5.0
    ) -> list[dict]:
        res = []
        with httpx.stream(
                "POST", self.api.completion,
                headers={
                    "authorization": self.auth,
                    "Cookie": self.cookie,
                    "Origin": "https://chat.deepseek.com",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
                    "Referer": f"https://chat.deepseek.com/a/chat/s/{self.session_id}",
                    "X-Ds-Pow-Response": "eyJhbGdvcml0aG0iOiJEZWVwU2Vla0hhc2hWMSIsImNoYWxsZW5nZSI6IjMwYjNkMjliZmM3YWMyOTkyOWIwYTgwMzNlOWQ5NGY5MDI2MzYwZDAxZGFiODZiYWQwNDdkNjVjNmJkM2NiNTUiLCJzYWx0IjoiYmE3OTE0MzAzMjA3MTg3YTBhNjQiLCJhbnN3ZXIiOjU3Mjg0LCJzaWduYXR1cmUiOiJiYzhjODI4OGZiODE0OTAxODlhYWI1ZDQ4MmNlZWI3Zjc5MzQ3NzJjNzgwNTAyODdmMTU3MGRkZWNmNTUyMGY5IiwidGFyZ2V0X3BhdGgiOiIvYXBpL3YwL2NoYXQvY29tcGxldGlvbiJ9"
                },
                json={
                    "chat_session_id": self.session_id,
                    "prompt": prompt,
                    "parent_message_id": self.get_code(),
                    "ref_file_ids": [],
                    "search_enabled": search,
                    "thinking_enabled": thinking
                },
                timeout=Timeout(timeout)
        ) as response:
            if response.status_code == 200:
                for i in response.iter_lines():
                    if i == "":
                        continue
                    elif i == "data: [DONE]":
                        break
                    else:
                        res.append(json.loads(i.replace("data: ", "")))
            else:
                print(f"请求失败，状态码: {response.status_code}")
        return res

    def chat(self, prompt: str, search: bool = False, thinking: bool = False, timeout: float = 5.0) -> Response:
        # return "".join(
        #     [
        #         i["choices"][0]["delta"].get("content") or ""
        #         for i in self.gen_completion(prompt, search, thinking, timeout)]
        # )
        rsp = Response("", "")
        for i in self.gen_completion(prompt, search, thinking, timeout):
            tp = i["choices"][0]["delta"].get("type")
            if not tp:
                break
            if tp == "thinking":
                rsp.thinking += i["choices"][0]["delta"].get("content", "")
            else:
                rsp.text += i["choices"][0]["delta"].get("content", "")
        return rsp

    def stream(self, prompt: str, search: bool = False, thinking: bool = False, timeout: float = 5.0) -> Iterator[str]:
        for i in self.gen_completion(prompt, search, thinking, timeout):
            yield str(i["choices"][0]["delta"].get("content") or "")

    def delete(self) -> None:
        response = httpx.post(
            self.api.delete_session,
            headers={"authorization": self.auth},
            json={"chat_session_id": self.session_id}
        )
        if response.json()["code"] != 0:
            print(response.text)
            raise Exception()

    def __del__(self) -> None:
        self.delete()
