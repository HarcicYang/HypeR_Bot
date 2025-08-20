import argparse
import traceback

from git import Repo

VERSION = "0.0.1"

hyparser = argparse.ArgumentParser(description=f"HypeR Bot Utils 版本 {VERSION}")

hyparser.add_argument(
    "-v", "--version",
    action="version",
    version=f"HypeR Bot 实用工具，版本 {VERSION}",
    help="显示版本信息"
)
hyparser.add_argument(
    "-i", "--install",
    action="store_true",
    help="安装完整的HypeR Bot到本地"
)
hyparser.add_argument(
    "-p", "--path",
    action="store",
    help="指定操作路径"
)


def clone(path: str):
    url = "https://github.com/HarcicYang/HypeR_Bot.git"
    Repo.clone_from(url, path, depth=1)


def main():
    args = hyparser.parse_args()
    if args.install:
        if args.path:
            print(f"将安装 HypeR Bot 到 {args.path}")
            print(f"正在克隆 HypeR Bot 到 {args.path}...")
            try:
                clone(args.path)
            except:
                traceback.print_exc()
                exit(1)
            print("完成，请前往目标目录运行 main.py 以继续设置")
        else:
            hyparser.error("您没有为 install 指定操作路径")
    else:
        hyparser.print_help()


if __name__ == "__main__":
    main()
