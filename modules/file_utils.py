import os


def file_url(path: str) -> str:
    return "file://" + os.path.abspath(path).replace("\\", "/")
