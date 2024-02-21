<div align="center">
<h1><img src="logo.ico" alt="icon" width="32px"> HypeR Bot</h1>
</div>
<p align="center">适配OneBot v11协议、功能模块化、易于扩展、高效的QQ机器人（框架？）</p>
<div align="center">
<img src="https://img.shields.io/badge/OneBot-11-black?logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAHAAAABwCAMAAADxPgR5AAAAGXRFWHRTb2Z0d2FyZQBBZG9iZSBJbWFnZVJlYWR5ccllPAAAAAxQTFRF////29vbr6+vAAAAk1hCcwAAAAR0Uk5T////AEAqqfQAAAKcSURBVHja7NrbctswDATQXfD//zlpO7FlmwAWIOnOtNaTM5JwDMa8E+PNFz7g3waJ24fviyDPgfhz8fHP39cBcBL9KoJbQUxjA2iYqHL3FAnvzhL4GtVNUcoSZe6eSHizBcK5LL7dBr2AUZlev1ARRHCljzRALIEog6H3U6bCIyqIZdAT0eBuJYaGiJaHSjmkYIZd+qSGWAQnIaz2OArVnX6vrItQvbhZJtVGB5qX9wKqCMkb9W7aexfCO/rwQRBzsDIsYx4AOz0nhAtWu7bqkEQBO0Pr+Ftjt5fFCUEbm0Sbgdu8WSgJ5NgH2iu46R/o1UcBXJsFusWF/QUaz3RwJMEgngfaGGdSxJkE/Yg4lOBryBiMwvAhZrVMUUvwqU7F05b5WLaUIN4M4hRocQQRnEedgsn7TZB3UCpRrIJwQfqvGwsg18EnI2uSVNC8t+0QmMXogvbPg/xk+Mnw/6kW/rraUlvqgmFreAA09xW5t0AFlHrQZ3CsgvZm0FbHNKyBmheBKIF2cCA8A600aHPmFtRB1XvMsJAiza7LpPog0UJwccKdzw8rdf8MyN2ePYF896LC5hTzdZqxb6VNXInaupARLDNBWgI8spq4T0Qb5H4vWfPmHo8OyB1ito+AysNNz0oglj1U955sjUN9d41LnrX2D/u7eRwxyOaOpfyevCWbTgDEoilsOnu7zsKhjRCsnD/QzhdkYLBLXjiK4f3UWmcx2M7PO21CKVTH84638NTplt6JIQH0ZwCNuiWAfvuLhdrcOYPVO9eW3A67l7hZtgaY9GZo9AFc6cryjoeFBIWeU+npnk/nLE0OxCHL1eQsc1IciehjpJv5mqCsjeopaH6r15/MrxNnVhu7tmcslay2gO2Z1QfcfX0JMACG41/u0RrI9QAAAABJRU5ErkJggg==" alt="Badge">
<img src="https://img.shields.io/static/v1?label=LICENSE&message=GPL-3.0&color=lightrey" alt="Badge">
</div>


## 概览
HypeR Bot是一个适配OneBot协议的机器人框架，旨在提供一个简洁、高效、可扩展的机器人运行结构。

## 文件结构
```tree
├── main.py
├── modules
│   ├── __init__.py
│   ├── ...
│   
├── lib
│   ├── Configuratior.py
│   ├── DataBase.py
│   ├── Listener.py
│   ├── Loogger.py
│   ├── Manager.py
│   ├── Segements.py
│   
├── config.json
```

## 配置文件
`config.json`:
```json
{
  "owner": [
    
  ],
  "black_list": [],
  "Connection": {
    "host": "127.0.0.1",
    "port": 5004
  },
  "Log_level": "INFO",
  "Others": {
    "Chat": {
      "Qwen": {
        "key": "key"
      }
    }
  }
}
```

其中：
- `owner`：机器人主人的QQ号，填写在这个列表中的QQ号会被标记`is_owner = True`；
- `black_list`：黑名单，填写在这个列表中的QQ号的消息不会被任何模块处理；
- `Connection`：连接信息，包括主机地址和端口；
- `Log_level`：日志等级，可选值为`DEBUG`、`TRACE`、`INFO`、`WARNING`、`ERROR`、`CRITICAL`；
- `Others`：其他配置项，这里的内容应当由各个功能模块的作者指定，示例中的`Chat`是用于实现调用[通义千问](https://dashscope.aliyun.com/)聊天功能的模块，其配置项为`Qwen`；


## 环境
> 本人开发和测试均在Python 3.11.7环境进行，其他版本未经测试。

所需的第三方库陈列在[`requirements.txt`](/requirements.txt)中，使用`pip install -r requirements.txt`即可。