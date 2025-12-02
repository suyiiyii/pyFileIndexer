#!/usr/bin/env python3
"""
pyFileIndexer 根目录入口点

这是 pyFileIndexer 的根目录入口文件，提供简单的方式启动应用程序。
它代理到 pyFileIndexer 包中的主模块。

使用方式:
    python main.py scan <path> [options]
    python main.py serve [options]
    python main.py merge [options]

或者使用包方式:
    python -m pyFileIndexer scan <path> [options]
    python -m pyFileIndexer serve [options]
    python -m pyFileIndexer merge [options]
"""

from pyFileIndexer.main import main

if __name__ == "__main__":
    main()
