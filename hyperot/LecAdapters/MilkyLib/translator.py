import httpx

from hyperot.network import HTTPConnection


class MilkyHttpConnection(HTTPConnection):
    def recv(self) -> dict:
        milky_rp =  self.reports.get()
        return milky_rp

    def send(self, endpoint: str, data: dict, echo: str) -> None:
        response = httpx.post(f"{self.url}/api/{endpoint}", json=data)
        res = response.json()
        res["echo"] = echo
        self.reports.put(res)
