import time
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

    def connect(self) -> None:
        self.ws.connect(self.url)

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

        self.listener_started = False

    def __start_listener(self) -> None:
        @self.app.route("/", methods=["POST"])
        def listener():
            self.reports.put(flask.request.json)
            return {}

            # self.app.run(host=self.listener_url, port=self.port)

        threading.Thread(target=lambda: self.app.run(host=self.listener_url, port=self.port)).start()
        self.listener_started = True

    def connect(self) -> None:
        if not self.listener_started:
            self.__start_listener()
        httpx.post(self.url)
        traceback.print_exc()

    def recv(self) -> dict:
        return self.reports.get()

    def send(self, endpoint: str, data: dict, echo: str) -> None:
        response = httpx.post(f"{self.url}/{endpoint}", json=data)
        res = response.json()
        res["echo"] = echo
        self.reports.put(res)

    @staticmethod
    def close() -> None:
        shutdown_func = flask.request.environ.get('werkzeug.server.shutdown')
        if shutdown_func is None:
            raise RuntimeError('Not running with the Werkzeug Server')
        shutdown_func()


class SatoriConnection:
    def __init__(self, host: str, port: int, token: str = None):
        self.ws = websocket.WebSocket()
        self.host = host
        self.port = port
        self.token = token
        self.reports = queue.Queue()

    def heart_beat(self) -> None:
        while 1:
            time.sleep(10)
            self.ws.send(json.dumps({"op": 1, "body": {}}))

    def connect(self) -> None:
        self.ws.connect(f"ws://{self.host}:{self.port}/v1/events")
        payload = {
            "op": 3,
            "body": {
                "token": self.token
            }
        }
        self.ws.send(json.dumps(payload))
        res = json.loads(self.ws.recv())
        if res["op"] == 4:
            threading.Thread(target=self.heart_beat).start()
        else:
            raise ConnectionError("连接失败")

    def send(self, payload: dict, echo: str = None) -> None:
        response = httpx.post(f"http://{self.host}:{self.port}", json=payload)
        try:
            data = response.json()
            data["echo"] = echo
            self.reports.put(data)
        except:
            pass

    def close(self) -> None:
        pass

    def recv(self) -> dict:
        return json.loads(self.ws.recv())

#
# class KritorConnection:
#     def __init__(self, host: str, port: int, account: str, ticket: str):
#         self.channel = grpc.insecure_channel(f"{host}:{port}")
#         self.account = account
#         self.ticket = ticket
#
#     def connect(self) -> None:
#         auth_stub = AuthenticationServiceStub(self.channel)
#         response = auth_stub.Authenticate(
#             AuthenticateRequest(
#                 account=self.account,
#                 ticket=self.ticket
#             )
#         )
#         if response.AuthenticateResponseCode != 0:
#             raise ConnectionError("鉴权失败")
#
#     def send(self, stub, payload: dict, echo: str = None) -> None:
#         response = httpx.post(f"http://{self.host}:{self.port}", json=payload)
#         try:
#             data = response.json()
#             data["echo"] = echo
#             self.reports.put(data)
#         except:
#             pass
#
#     def close(self) -> None:
#         pass
#
#     def recv(self) -> dict:
#         return json.loads(self.ws.recv())
