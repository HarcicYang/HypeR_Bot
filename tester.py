import httpx

response1 = httpx.post(
    "https://sign.lagrangecore.org/api/sign/sec-sign",
    headers={"Content-Type": "application/json", "Authorization": "Bearer 85a20362-dc40-4ea3-b4ec-a6d0b9c8d422"},
    json={
        "uin": 3672492480,
        "command": "MessageSvc.PbSendMsg",
        "seq": 8954,
        "body": "0a08120608c8c79fa90212060801100018001a4f0a4d123e0a3c0a07404861726369631a0d000100000007009453f23b000062221802200028004a18755f6763445f4664794c646255526f6246547053737248775800120b0a090a073139313938313020fb4528bbfab0b906",
        "guid": "cfcd208495d565ef66e7dff9f98764da",
        "qua": "V1_LNX_NQ_3.2.26_46494_GW_B",
    },
)

response2 = httpx.post(
    "https://sign.lagrangecore.org/api/sign/sec-sign",
    headers={"Content-Type": "application/json", "Authorization": "Bearer 85a20362-dc40-4ea3-b4ec-a6d0b9c8d422"},
    json={
        "uin": 3672492480,
        "command": "MessageSvc.PbSendMsg",
        "seq": 8954,
        "body": "0a08120608c8c79fa90212060801100018001a4f0a4d123e0a3c0a07404861726369631a0d000100000007009453f23b000062221802200028004a18755f6763445f4664794c646255526f6246547053737248775800120b0a090a073139313938313020fb4528bbfab0b906",
        "guid": "cfcd208495d565ef66e7dff9f98764da",
        "qua": "V1_LNX_NQ_3.2.26_46494_GW_B",
    },
)


print(response1.content.decode() == response2.content.decode())
