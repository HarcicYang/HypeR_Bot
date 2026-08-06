from typing import Any, cast

import requests
from flask import Flask, request
from werkzeug.wrappers.response import Response as WerkzeugResponse

app = Flask(__name__)

# 目标 URL
TARGET_URL = "https://fancy-king-a740.harcic4690.workers.dev:443"


@app.route("/", defaults={"path": ""}, methods=["GET", "POST"])
@app.route("/<path:path>", methods=["GET", "POST"])
def proxy(path: str):
    headers: dict[str, Any] = {key: value for (key, value) in request.headers if key != "Host"}
    resp = requests.request(
        method=request.method,
        url=TARGET_URL + request.full_path,
        headers=headers,
        data=request.get_data(),
        cookies=request.cookies,
        allow_redirects=False,
    )

    excluded_headers = ["content-encoding", "content-length", "transfer-encoding", "connection"]
    resp_headers = [(name, value) for (name, value) in resp.raw.headers.items() if name.lower() not in excluded_headers]

    response = cast(WerkzeugResponse, app.response_class(status=resp.status_code, headers=resp_headers))
    response.set_data(resp.content)
    return response


if __name__ == "__main__":
    # 注意：在生产环境中，请使用更安全的方法启动 Flask
    app.run(host="127.0.0.1", port=80, debug=True)
