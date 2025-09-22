# pyFileIndexer 性能测试工具

`benchmark.py` 是一个独立的性能测试脚本，通过 CLI 调用 pyFileIndexer 来测试程序性能，不涉及内部逻辑。

## 功能特性

### 🚀 测试场景
- **规模性能测试**: 小规模(100文件)、中规模(1000文件)、大规模(5000文件)
- **增量扫描测试**: 测试重复扫描的性能提升
- **文件修改测试**: 测试部分文件修改后的扫描性能
- **并发性能测试**: 多轮测试验证性能稳定性

### 📊 性能指标
- **扫描性能**: 总扫描时间、文件处理速度(文件/秒)、吞吐量(MB/秒)
- **数据库性能**: 数据库文件大小、记录数量
- **系统资源**: CPU使用率、内存占用
- **批量操作效果**: 对比不同规模下的性能表现

### 📈 测试数据
- **多样化文件**: 文本文件(70%)、二进制文件(20%)、空文件(10%)
- **重复文件**: 10% 重复文件测试哈希去重性能
- **随机大小**: 1KB - 10MB 的随机文件大小
- **真实场景**: 模拟实际使用中的文件分布

## 使用方法

### 基本用法

```bash
# 使用默认配置运行
uv run python benchmark.py

# 自定义测试规模
uv run python benchmark.py --small 50 --medium 500 --large 2000

# 指定测试轮数和输出目录
uv run python benchmark.py --rounds 5 --output my_benchmark_results

# 设置机器名称标识
uv run python benchmark.py --machine-name my-laptop
```

### 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--small` | 100 | 小规模测试文件数量 |
| `--medium` | 1000 | 中规模测试文件数量 |
| `--large` | 5000 | 大规模测试文件数量 |
| `--rounds` | 3 | 每个测试的运行轮数 |
| `--output` | benchmark_results | 输出目录 |
| `--machine-name` | benchmark-test | 机器名称标识 |

### 快速测试

```bash
# 快速小规模测试 (适用于开发验证)
uv run python benchmark.py --small 10 --medium 50 --large 100 --rounds 1

# 完整性能测试 (适用于性能评估)
uv run python benchmark.py --small 200 --medium 2000 --large 10000 --rounds 5
```

## 测试报告

### 输出文件

运行完成后会在指定目录生成以下报告：

1. **benchmark_results.json**: JSON 格式详细数据，包含所有测试指标
2. **benchmark_report.txt**: 人类可读的详细报告
3. **benchmark_summary.txt**: 汇总统计信息

### 报告示例

```
性能测试汇总统计
========================================

SMALL 规模测试统计:
------------------------------
平均处理速度: 19.4 文件/秒
平均吞吐量: 75.09 MB/秒
平均扫描时间: 0.26 秒
测试轮数: 1

MEDIUM 规模测试统计:
------------------------------
平均处理速度: 57.3 文件/秒
平均吞吐量: 219.19 MB/秒
平均扫描时间: 0.35 秒
测试轮数: 1
```

## 性能分析

### 关键指标

- **文件/秒**: 每秒处理的文件数量，反映处理效率
- **MB/秒**: 每秒处理的数据量，反映I/O性能
- **增量扫描倍数**: 重复扫描vs首次扫描的性能提升
- **内存使用**: 扫描过程中的内存占用
- **数据库效率**: 数据库大小与文件数量的比率

### 性能优化验证

使用 benchmark 可以验证以下优化效果：

1. **批量数据库操作**: 对比批量前后的性能提升
2. **哈希去重**: 重复文件的处理效率
3. **增量扫描**: 未修改文件的跳过效果
4. **并发处理**: 多线程带来的性能提升

## CI/CD 集成

### 性能回归检测

```bash
# 在CI中运行基准测试
uv run python benchmark.py --small 100 --medium 1000 --rounds 3 --output ci_benchmark

# 比较历史性能数据
# 可以将 benchmark_results.json 与历史数据对比，检测性能回归
```

### 示例 GitHub Actions

```yaml
name: Performance Benchmark
on: [push, pull_request]

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install uv
          uv sync
      - name: Run benchmark
        run: uv run python benchmark.py --rounds 3 --output benchmark_results
      - name: Upload benchmark results
        uses: actions/upload-artifact@v3
        with:
          name: benchmark-results
          path: benchmark_results/
```

## 注意事项

1. **测试环境**: 确保测试环境相对稳定，避免其他进程干扰
2. **磁盘空间**: 大规模测试会生成大量临时文件，确保有足够磁盘空间
3. **运行时间**: 大规模测试可能需要较长时间，建议合理设置超时
4. **资源监控**: 在macOS上IO监控可能不可用，但不影响其他指标

## 故障排除

### 常见问题

1. **依赖缺失**: 确保已安装 `psutil` 依赖
   ```bash
   uv sync  # 同步所有依赖
   ```

2. **权限问题**: 确保有临时目录的读写权限

3. **超时错误**: 大规模测试可能超时，可以调整 `_run_single_scan` 中的超时设置

4. **IO监控不可用**: 在某些系统上正常，不影响其他性能指标

### 调试模式

修改 `benchmark.py` 中的日志级别或添加调试输出：

```python
# 在 _run_single_scan 中添加调试信息
print(f"CLI 命令: {' '.join(cmd)}")
print(f"CLI 输出: {result.stdout}")
```

## 扩展功能

可以根据需要扩展以下功能：

1. **Web界面测试**: 添加Web服务器性能测试
2. **网络存储测试**: 测试网络文件系统的性能
3. **内存使用优化**: 添加内存使用峰值监控
4. **多机器对比**: 不同机器间的性能对比

---

通过 benchmark 工具，可以全面评估 pyFileIndexer 的性能表现，验证优化效果，确保在不同规模下的稳定运行。