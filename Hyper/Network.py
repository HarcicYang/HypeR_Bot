import websocket
import httpx
import queue
import flask
import traceback
import json
import logging
import threading


class WebsocketConnection:
    def __init__(self, url: str):
        self.ws = websocket.WebSocket()
        self.url = url

    def connect(self) -> bool:
        try:
            self.ws.connect(self.url)
        except:
            traceback.print_exc()
            return False

        return True

    def send(self, message: str) -> None:
        self.ws.send(message)

    def close(self) -> None:
        self.ws.close()

    def recv(self) -> dict:
        return json.loads(self.ws.recv())


class HTTPConnection:
    def __init__(self, url: str, listener_url: str):
        self.url = url
        listener_url = listener_url.replace("http://", "")
        listener_url = listener_url.replace("https://", "")
        self.listener_url = listener_url.split(":")[0]
        try:
            self.port = int(listener_url.split(":")[1])
        except IndexError:
            self.port = 8080
        self.app = flask.Flask(__name__)
        self.app.config["LOGGER_HANDLER_POLICY"] = "never"
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        self.reports = queue.Queue()

    def connect(self) -> bool:
        @self.app.route("/", methods=["POST"])
        def listener():
            self.reports.put(flask.request.json)
            return {}

        try:
            # self.app.run(host=self.listener_url, port=self.port)
            threading.Thread(target=lambda: self.app.run(host=self.listener_url, port=self.port)).start()
        except:
            traceback.print_exc()
            return False
        finally:
            try:
                httpx.post(self.url)
            except:
                traceback.print_exc()
                return False

        return True

    def recv(self) -> dict:
        return self.reports.get()

    def send(self, endpoint: str, data: dict, echo: str) -> None:
        response = httpx.post(f"{self.url}/{endpoint}", json=data)
        res = response.json()
        res["echo"] = echo
        self.reports.put(res)
