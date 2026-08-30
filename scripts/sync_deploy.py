"""deploy/api 镜像副本同步脚本（v6.8.0 起已废弃）。

历史背景：v6.8.0 前 deploy/api 是线上部署副本，根 api 是开发源，
本脚本用逐文件哈希对比防漂移。v6.8.0 起 build context 改为仓库根（..），
部署直接用根 api/ 源码构建，deploy/api 副本已删除，本脚本不再需要。

保留入口仅为向后兼容（CI/文档旧引用），任何 action 均打印废弃提示并 exit 0。
"""

import sys


def main() -> int:
    print("v6.8.0: deploy/api 镜像副本已废除，build context 改为仓库根（..），")
    print("部署直接用根 api/ 源码构建，sync_deploy.py 不再需要同步。")
    print("若仍存在 deploy/api/ 目录，请删除（git rm -r deploy/api）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
