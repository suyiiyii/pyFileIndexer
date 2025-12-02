#!/usr/bin/env python3
"""
pyFileIndexer 性能测试脚本

完全通过 CLI 调用 pyFileIndexer 进行性能测试，不涉及内部逻辑。
测试包括扫描性能、数据库操作性能、系统资源使用等。
"""

import argparse
import json
import psutil
import random
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class TestConfig:
    """测试配置"""

    small_files: int = 100
    medium_files: int = 1000
    large_files: int = 5000
    file_size_range: Tuple[int, int] = (1024, 10 * 1024 * 1024)  # 1KB - 10MB
    duplicate_ratio: float = 0.1  # 10% 重复文件
    machine_name: str = "benchmark-test"
    test_rounds: int = 3  # 每个测试运行次数


@dataclass
class ResourceMetrics:
    """系统资源指标"""

    timestamp: float
    cpu_percent: float
    memory_mb: float
    disk_io_read_mb: float
    disk_io_write_mb: float


@dataclass
class PerformanceResult:
    """性能测试结果"""

    test_name: str
    file_count: int
    total_size_mb: float
    scan_time_seconds: float
    files_per_second: float
    mb_per_second: float
    db_size_mb: float
    db_records: int
    resource_metrics: List[ResourceMetrics]
    cli_output: str


class ResourceMonitor:
    """系统资源监控器"""

    def __init__(self, interval: float = 0.5):
        self.interval = interval
        self.metrics: List[ResourceMetrics] = []
        self.monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None

    def start(self):
        """开始监控"""
        self.metrics.clear()
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop)
        self.monitor_thread.start()

    def stop(self) -> List[ResourceMetrics]:
        """停止监控并返回指标"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join()
        return self.metrics.copy()

    def _monitor_loop(self):
        """监控循环"""
        process = psutil.Process()

        # 尝试获取 I/O 计数器，如果不支持则使用 0
        try:
            last_io = process.io_counters()
            io_supported = True
        except (AttributeError, OSError):
            last_io = None
            io_supported = False

        while self.monitoring:
            disk_io_read_mb = 0
            disk_io_write_mb = 0

            if io_supported:
                try:
                    current_io = process.io_counters()
                    disk_io_read_mb = (
                        (current_io.read_bytes - last_io.read_bytes) / 1024 / 1024
                    )
                    disk_io_write_mb = (
                        (current_io.write_bytes - last_io.write_bytes) / 1024 / 1024
                    )
                    last_io = current_io
                except (AttributeError, OSError):
                    io_supported = False

            metric = ResourceMetrics(
                timestamp=time.time(),
                cpu_percent=process.cpu_percent(),
                memory_mb=process.memory_info().rss / 1024 / 1024,
                disk_io_read_mb=disk_io_read_mb,
                disk_io_write_mb=disk_io_write_mb,
            )

            self.metrics.append(metric)
            time.sleep(self.interval)


class TestDataGenerator:
    """测试数据生成器"""

    @staticmethod
    def create_test_files(
        base_dir: Path, file_count: int, config: TestConfig
    ) -> Dict[str, any]:
        """创建测试文件"""
        base_dir.mkdir(parents=True, exist_ok=True)

        files_info = {
            "total_files": file_count,
            "total_size": 0,
            "duplicate_files": 0,
            "file_types": {"text": 0, "binary": 0, "empty": 0},
        }

        # 生成基础文件
        duplicate_count = int(file_count * config.duplicate_ratio)
        unique_count = file_count - duplicate_count

        # 创建唯一文件
        for i in range(unique_count):
            file_path = base_dir / f"file_{i:06d}.txt"
            file_type, size = TestDataGenerator._create_single_file(file_path, config)
            files_info["total_size"] += size
            files_info["file_types"][file_type] += 1

        # 创建重复文件（复制已有文件）
        for i in range(duplicate_count):
            source_idx = random.randint(
                0, min(unique_count - 1, 50)
            )  # 从前50个文件中选择
            source_file = base_dir / f"file_{source_idx:06d}.txt"
            if source_file.exists():
                duplicate_file = base_dir / f"duplicate_{i:06d}.txt"
                shutil.copy2(source_file, duplicate_file)
                files_info["total_size"] += source_file.stat().st_size
                files_info["duplicate_files"] += 1
                files_info["file_types"]["text"] += 1

        return files_info

    @staticmethod
    def _create_single_file(file_path: Path, config: TestConfig) -> Tuple[str, int]:
        """创建单个文件"""
        min_size, max_size = config.file_size_range

        # 决定文件类型和大小
        rand = random.random()
        if rand < 0.1:  # 10% 空文件
            file_path.touch()
            return "empty", 0
        elif rand < 0.3:  # 20% 二进制文件
            size = random.randint(
                min_size, min(max_size, 1024 * 1024)
            )  # 二进制文件不超过1MB
            content = bytes([random.randint(0, 255) for _ in range(size)])
            file_path.write_bytes(content)
            return "binary", size
        else:  # 70% 文本文件
            size = random.randint(min_size, max_size)
            lines = []
            current_size = 0
            while current_size < size:
                line = f"Line {len(lines):06d}: " + "x" * random.randint(10, 100) + "\n"
                lines.append(line)
                current_size += len(line.encode())

            content = "".join(lines)
            file_path.write_text(content)
            return "text", len(content.encode())


class BenchmarkRunner:
    """性能测试运行器"""

    def __init__(self, config: TestConfig):
        self.config = config
        self.project_root = Path(__file__).parent
        self.temp_dir: Optional[Path] = None
        self.results: List[PerformanceResult] = []

    def run_all_benchmarks(self) -> List[PerformanceResult]:
        """运行所有性能测试"""
        print("🚀 开始 pyFileIndexer 性能测试")
        print(f"测试配置: {self.config}")
        print("-" * 60)

        try:
            self.temp_dir = Path(tempfile.mkdtemp(prefix="pyfileindexer_benchmark_"))
            print(f"测试目录: {self.temp_dir}")

            # 小规模测试
            self._run_scale_test("small", self.config.small_files)

            # 中规模测试
            self._run_scale_test("medium", self.config.medium_files)

            # 大规模测试
            self._run_scale_test("large", self.config.large_files)

            # 增量扫描测试
            self._run_incremental_test()

            # 修改文件测试
            self._run_modification_test()

        finally:
            if self.temp_dir and self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)

        return self.results

    def _run_scale_test(self, scale_name: str, file_count: int):
        """运行特定规模的测试"""
        print(f"\n📊 运行 {scale_name} 规模测试 ({file_count} 文件)")

        test_dir = self.temp_dir / f"test_{scale_name}"
        db_path = self.temp_dir / f"test_{scale_name}.db"

        # 生成测试数据
        print("  生成测试文件...")
        files_info = TestDataGenerator.create_test_files(
            test_dir, file_count, self.config
        )
        print(
            f"  创建了 {files_info['total_files']} 个文件，总大小 {files_info['total_size'] / 1024 / 1024:.2f} MB"
        )

        # 运行性能测试
        for round_num in range(self.config.test_rounds):
            print(f"  第 {round_num + 1}/{self.config.test_rounds} 轮测试...")

            # 删除之前的数据库
            if db_path.exists():
                db_path.unlink()

            result = self._run_single_scan(
                f"{scale_name}_round_{round_num + 1}",
                test_dir,
                db_path,
                files_info["total_files"],
                files_info["total_size"] / 1024 / 1024,
            )

            if result:
                self.results.append(result)
                print(f"    扫描时间: {result.scan_time_seconds:.2f}s")
                print(f"    处理速度: {result.files_per_second:.1f} 文件/秒")
                print(f"    吞吐量: {result.mb_per_second:.2f} MB/秒")

    def _run_incremental_test(self):
        """运行增量扫描测试"""
        print("\n🔄 运行增量扫描测试")

        test_dir = self.temp_dir / "test_incremental"
        db_path = self.temp_dir / "test_incremental.db"

        # 首次扫描
        files_info = TestDataGenerator.create_test_files(
            test_dir, self.config.medium_files, self.config
        )

        print("  首次扫描...")
        first_result = self._run_single_scan(
            "incremental_first_scan",
            test_dir,
            db_path,
            files_info["total_files"],
            files_info["total_size"] / 1024 / 1024,
        )

        if first_result:
            self.results.append(first_result)

        # 重复扫描（应该跳过大部分文件）
        print("  重复扫描（增量）...")
        second_result = self._run_single_scan(
            "incremental_repeat_scan",
            test_dir,
            db_path,
            files_info["total_files"],
            files_info["total_size"] / 1024 / 1024,
        )

        if second_result:
            self.results.append(second_result)
            print(
                f"  性能提升: {first_result.scan_time_seconds / second_result.scan_time_seconds:.2f}x"
            )

    def _run_modification_test(self):
        """运行文件修改测试"""
        print("\n📝 运行文件修改测试")

        test_dir = self.temp_dir / "test_modification"
        db_path = self.temp_dir / "test_modification.db"

        # 创建初始文件并扫描
        files_info = TestDataGenerator.create_test_files(
            test_dir, self.config.small_files, self.config
        )

        self._run_single_scan(
            "modification_initial",
            test_dir,
            db_path,
            files_info["total_files"],
            files_info["total_size"] / 1024 / 1024,
        )

        # 修改部分文件
        print("  修改 20% 的文件...")
        files_to_modify = int(files_info["total_files"] * 0.2)
        for i in range(files_to_modify):
            file_path = test_dir / f"file_{i:06d}.txt"
            if file_path.exists():
                try:
                    # 尝试作为文本文件读取和修改
                    content = (
                        file_path.read_text(encoding="utf-8") + "\nModified content"
                    )
                    file_path.write_text(content, encoding="utf-8")
                except UnicodeDecodeError:
                    # 如果是二进制文件，则添加一些字节
                    content = file_path.read_bytes()
                    content += b"\nModified binary content"
                    file_path.write_bytes(content)

        # 重新扫描修改后的文件
        print("  扫描修改后的文件...")
        modified_result = self._run_single_scan(
            "modification_after_changes",
            test_dir,
            db_path,
            files_info["total_files"],
            files_info["total_size"] / 1024 / 1024,
        )

        if modified_result:
            self.results.append(modified_result)

    def _run_single_scan(
        self,
        test_name: str,
        scan_dir: Path,
        db_path: Path,
        file_count: int,
        total_size_mb: float,
    ) -> Optional[PerformanceResult]:
        """运行单次扫描测试"""
        monitor = ResourceMonitor()

        # 构建 CLI 命令
        cmd = [
            "uv",
            "run",
            "python",
            "pyFileIndexer/main.py",
            str(scan_dir),
            "--machine_name",
            self.config.machine_name,
            "--db_path",
            str(db_path),
            "--log_path",
            str(self.temp_dir / f"{test_name}.log"),
        ]

        try:
            # 开始监控
            monitor.start()
            start_time = time.time()

            # 运行命令
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=300,  # 5分钟超时
            )

            end_time = time.time()
            resource_metrics = monitor.stop()

            if result.returncode != 0:
                print("    错误: CLI 命令执行失败")
                print(f"    stdout: {result.stdout}")
                print(f"    stderr: {result.stderr}")
                return None

            # 计算性能指标
            scan_time = end_time - start_time
            files_per_second = file_count / scan_time if scan_time > 0 else 0
            mb_per_second = total_size_mb / scan_time if scan_time > 0 else 0

            # 获取数据库信息
            db_size_mb = 0
            db_records = 0
            if db_path.exists():
                db_size_mb = db_path.stat().st_size / 1024 / 1024
                db_records = self._count_db_records(db_path)

            return PerformanceResult(
                test_name=test_name,
                file_count=file_count,
                total_size_mb=total_size_mb,
                scan_time_seconds=scan_time,
                files_per_second=files_per_second,
                mb_per_second=mb_per_second,
                db_size_mb=db_size_mb,
                db_records=db_records,
                resource_metrics=resource_metrics,
                cli_output=result.stdout + result.stderr,
            )

        except subprocess.TimeoutExpired:
            monitor.stop()
            print("    错误: 测试超时")
            return None
        except Exception as e:
            monitor.stop()
            print(f"    错误: {e}")
            return None

    def _count_db_records(self, db_path: Path) -> int:
        """统计数据库记录数"""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM file_meta")
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except Exception:
            return 0


class BenchmarkReporter:
    """性能测试报告生成器"""

    @staticmethod
    def generate_report(results: List[PerformanceResult], output_dir: Path):
        """生成性能测试报告"""
        output_dir.mkdir(parents=True, exist_ok=True)

        # 生成 JSON 报告
        json_path = output_dir / "benchmark_results.json"
        BenchmarkReporter._generate_json_report(results, json_path)

        # 生成文本报告
        text_path = output_dir / "benchmark_report.txt"
        BenchmarkReporter._generate_text_report(results, text_path)

        # 生成汇总统计
        summary_path = output_dir / "benchmark_summary.txt"
        BenchmarkReporter._generate_summary_report(results, summary_path)

        print("\n📊 报告已生成:")
        print(f"  JSON 详细报告: {json_path}")
        print(f"  文本报告: {text_path}")
        print(f"  汇总报告: {summary_path}")

    @staticmethod
    def _generate_json_report(results: List[PerformanceResult], output_path: Path):
        """生成 JSON 格式报告"""
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "total_tests": len(results),
            "results": [asdict(result) for result in results],
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

    @staticmethod
    def _generate_text_report(results: List[PerformanceResult], output_path: Path):
        """生成文本格式报告"""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("pyFileIndexer 性能测试报告\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"总测试数: {len(results)}\n\n")

            for result in results:
                f.write(f"测试: {result.test_name}\n")
                f.write("-" * 40 + "\n")
                f.write(f"文件数量: {result.file_count:,}\n")
                f.write(f"总大小: {result.total_size_mb:.2f} MB\n")
                f.write(f"扫描时间: {result.scan_time_seconds:.2f} 秒\n")
                f.write(f"处理速度: {result.files_per_second:.1f} 文件/秒\n")
                f.write(f"吞吐量: {result.mb_per_second:.2f} MB/秒\n")
                f.write(f"数据库大小: {result.db_size_mb:.2f} MB\n")
                f.write(f"数据库记录: {result.db_records:,}\n")

                if result.resource_metrics:
                    avg_cpu = sum(m.cpu_percent for m in result.resource_metrics) / len(
                        result.resource_metrics
                    )
                    avg_memory = sum(
                        m.memory_mb for m in result.resource_metrics
                    ) / len(result.resource_metrics)
                    f.write(f"平均CPU使用: {avg_cpu:.1f}%\n")
                    f.write(f"平均内存使用: {avg_memory:.1f} MB\n")

                f.write("\n")

    @staticmethod
    def _generate_summary_report(results: List[PerformanceResult], output_path: Path):
        """生成汇总统计报告"""
        if not results:
            return

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("性能测试汇总统计\n")
            f.write("=" * 40 + "\n\n")

            # 按规模分组统计
            scale_groups = {}
            for result in results:
                if "small" in result.test_name:
                    scale = "small"
                elif "medium" in result.test_name:
                    scale = "medium"
                elif "large" in result.test_name:
                    scale = "large"
                else:
                    scale = "other"

                if scale not in scale_groups:
                    scale_groups[scale] = []
                scale_groups[scale].append(result)

            for scale, group_results in scale_groups.items():
                if not group_results:
                    continue

                f.write(f"{scale.upper()} 规模测试统计:\n")
                f.write("-" * 30 + "\n")

                avg_files_per_sec = sum(
                    r.files_per_second for r in group_results
                ) / len(group_results)
                avg_mb_per_sec = sum(r.mb_per_second for r in group_results) / len(
                    group_results
                )
                avg_scan_time = sum(r.scan_time_seconds for r in group_results) / len(
                    group_results
                )

                f.write(f"平均处理速度: {avg_files_per_sec:.1f} 文件/秒\n")
                f.write(f"平均吞吐量: {avg_mb_per_sec:.2f} MB/秒\n")
                f.write(f"平均扫描时间: {avg_scan_time:.2f} 秒\n")
                f.write(f"测试轮数: {len(group_results)}\n\n")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="pyFileIndexer 性能测试工具")

    parser.add_argument(
        "--small", type=int, default=100, help="小规模测试文件数量 (默认: 100)"
    )
    parser.add_argument(
        "--medium", type=int, default=1000, help="中规模测试文件数量 (默认: 1000)"
    )
    parser.add_argument(
        "--large", type=int, default=5000, help="大规模测试文件数量 (默认: 5000)"
    )
    parser.add_argument(
        "--rounds", type=int, default=3, help="每个测试的运行轮数 (默认: 3)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="benchmark_results",
        help="输出目录 (默认: benchmark_results)",
    )
    parser.add_argument(
        "--machine-name",
        type=str,
        default="benchmark-test",
        help="机器名称标识 (默认: benchmark-test)",
    )

    args = parser.parse_args()

    # 创建测试配置
    config = TestConfig(
        small_files=args.small,
        medium_files=args.medium,
        large_files=args.large,
        test_rounds=args.rounds,
        machine_name=args.machine_name,
    )

    # 运行性能测试
    runner = BenchmarkRunner(config)
    results = runner.run_all_benchmarks()

    # 生成报告
    output_dir = Path(args.output)
    BenchmarkReporter.generate_report(results, output_dir)

    print(f"\n✅ 性能测试完成! 共运行 {len(results)} 个测试")
    if results:
        total_files = sum(r.file_count for r in results)
        avg_speed = sum(r.files_per_second for r in results) / len(results)
        print(f"总处理文件: {total_files:,}")
        print(f"平均处理速度: {avg_speed:.1f} 文件/秒")


if __name__ == "__main__":
    main()
