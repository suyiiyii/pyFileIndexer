#!/usr/bin/env python3
"""
测试运行脚本

提供便捷的测试执行和结果查看功能
"""

import sys
import subprocess
import argparse
from pathlib import Path


def run_command(cmd, description=""):
    """运行命令并处理结果"""
    print(f"\n{'='*60}")
    print(f"运行: {description}")
    print(f"命令: {' '.join(cmd)}")
    print(f"{'='*60}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.stdout:
            print("标准输出:")
            print(result.stdout)

        if result.stderr:
            print("错误输出:")
            print(result.stderr)

        if result.returncode != 0:
            print(f"命令执行失败，返回码: {result.returncode}")
            return False
        else:
            print("命令执行成功")
            return True

    except Exception as e:
        print(f"执行命令时发生错误: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="pyFileIndexer 测试运行器")

    parser.add_argument(
        "--type", "-t",
        choices=["unit", "integration", "all", "coverage", "lint"],
        default="all",
        help="测试类型"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="详细输出"
    )

    parser.add_argument(
        "--parallel", "-p",
        action="store_true",
        help="并行运行测试"
    )

    parser.add_argument(
        "--module", "-m",
        help="指定测试模块 (例如: test_models)"
    )

    parser.add_argument(
        "--function", "-f",
        help="指定测试函数 (例如: test_file_hash_creation)"
    )

    args = parser.parse_args()

    # 检查是否在项目根目录
    project_root = Path(__file__).parent
    if not (project_root / "pyFileIndexer").exists():
        print("错误: 请在项目根目录运行此脚本")
        sys.exit(1)

    # 基础 pytest 命令
    base_cmd = ["python", "-m", "pytest"]

    if args.verbose:
        base_cmd.append("-v")

    if args.parallel:
        base_cmd.extend(["-n", "auto"])

    success = True

    if args.type == "lint":
        # 代码检查
        print("运行代码检查...")

        # ruff 检查
        if not run_command(["ruff", "check", "pyFileIndexer/"], "Ruff 代码检查"):
            success = False

        # mypy 类型检查
        if not run_command(["mypy", "pyFileIndexer/"], "MyPy 类型检查"):
            success = False

    elif args.type == "unit":
        # 单元测试
        cmd = base_cmd + ["-m", "unit", "tests/"]
        if not run_command(cmd, "单元测试"):
            success = False

    elif args.type == "integration":
        # 集成测试
        cmd = base_cmd + ["-m", "integration", "tests/"]
        if not run_command(cmd, "集成测试"):
            success = False

    elif args.type == "coverage":
        # 覆盖率测试
        cmd = base_cmd + [
            "--cov=pyFileIndexer",
            "--cov-report=html",
            "--cov-report=term-missing",
            "tests/"
        ]
        if not run_command(cmd, "覆盖率测试"):
            success = False
        else:
            print("\n覆盖率报告已生成到 htmlcov/ 目录")

    elif args.type == "all":
        # 运行所有测试
        print("运行完整测试套件...")

        # 先运行快速的单元测试
        cmd = base_cmd + ["-m", "unit and not slow", "tests/"]
        if not run_command(cmd, "快速单元测试"):
            success = False

        # 然后运行集成测试
        cmd = base_cmd + ["-m", "integration", "tests/"]
        if not run_command(cmd, "集成测试"):
            success = False

        # 最后运行慢速测试
        cmd = base_cmd + ["-m", "slow", "tests/"]
        if not run_command(cmd, "性能测试"):
            success = False

    # 处理特定模块或函数测试
    if args.module or args.function:
        test_path = "tests/"

        if args.module:
            if not args.module.startswith("test_"):
                args.module = "test_" + args.module
            if not args.module.endswith(".py"):
                args.module += ".py"
            test_path = f"tests/{args.module}"

        if args.function:
            test_path += f"::{args.function}"

        cmd = base_cmd + [test_path]
        if not run_command(cmd, f"指定测试: {test_path}"):
            success = False

    if success:
        print("\n🎉 所有测试都通过了!")
        print("\n下一步:")
        print("1. 查看覆盖率报告: open htmlcov/index.html")
        print("2. 运行完整测试: python run_tests.py -t all")
        print("3. 运行性能测试: python run_tests.py -t all -m slow")
    else:
        print("\n❌ 有测试失败了")
        print("\n调试建议:")
        print("1. 查看上面的错误输出")
        print("2. 运行特定失败的测试: python run_tests.py -m <test_file> -f <test_function>")
        print("3. 使用详细模式: python run_tests.py -v")
        sys.exit(1)


if __name__ == "__main__":
    main()