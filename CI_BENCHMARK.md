# CI 性能测试文档

## 概述

项目配置了自动化性能测试 CI workflow，在每次创建版本标签时自动运行 benchmark 测试，并将结果上传为 GitHub artifacts。

## 触发方式

### 1. 自动触发（推荐）

当推送 `v*` 格式的标签时自动触发：

```bash
# 创建并推送标签
git tag v1.0.0
git push origin v1.0.0

# 或者一次性创建带注释的标签
git tag -a v1.0.0 -m "Release version 1.0.0"
git push origin v1.0.0
```

### 2. 手动触发

在 GitHub 仓库的 Actions 页面，可以手动运行 "Performance Benchmark" workflow：

1. 进入 GitHub 仓库
2. 点击 "Actions" 标签
3. 选择 "Performance Benchmark" workflow
4. 点击 "Run workflow"
5. 可选择自定义参数：
   - Tag name: 标签名称（默认: manual-run）
   - Small files: 小规模测试文件数（默认: 200）
   - Medium files: 中规模测试文件数（默认: 2000）
   - Large files: 大规模测试文件数（默认: 8000）

## 测试配置

### 默认测试参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| Small files | 200 | 小规模测试文件数量 |
| Medium files | 2000 | 中规模测试文件数量 |
| Large files | 8000 | 大规模测试文件数量 |
| Test rounds | 3 | 每个规模的测试轮数 |
| Timeout | 30 分钟 | 单个测试的超时时间 |

### 测试环境

- **操作系统**: Ubuntu Latest
- **Python 版本**: 3.11
- **运行器**: GitHub Actions (标准配置)
- **依赖管理**: uv
- **前端构建**: 包含 React 前端构建

## 输出结果

### Artifacts 内容

每次运行会生成一个命名为 `benchmark-results-{version}-{timestamp}` 的 artifact，包含：

| 文件 | 说明 |
|------|------|
| `benchmark_results.json` | 完整的性能数据（机器可读） |
| `benchmark_report.txt` | 人类可读的详细报告 |
| `benchmark_summary.txt` | 汇总统计信息 |
| `benchmark_run.log` | 完整的执行日志 |
| `system_info.txt` | 测试环境系统信息 |
| `metadata.json` | 测试元数据（版本、commit等） |
| `key_metrics.txt` | 关键性能指标提取 |
| `PERFORMANCE_SUMMARY.md` | Markdown 格式的性能总结 |

### Release 集成

当标签触发时，性能测试结果会自动添加到 GitHub Release 中：

- Release 描述包含关键性能指标
- `PERFORMANCE_SUMMARY.md` 文件附加到 Release
- 详细的 benchmark artifacts 链接

## 性能指标

### 关键指标

- **文件处理速度**: 文件/秒
- **数据吞吐量**: MB/秒
- **扫描时间**: 总扫描时长
- **内存使用**: 平均内存占用
- **数据库效率**: 数据库大小与记录数比率

### 测试场景

1. **规模性能**: 不同文件数量下的性能表现
2. **增量扫描**: 重复扫描的性能提升
3. **文件修改**: 部分文件修改后的扫描效率
4. **稳定性测试**: 多轮测试验证性能一致性

## 性能分析

### 查看结果

1. **GitHub Actions 页面**:
   - 查看实时运行日志
   - 下载完整的 artifacts

2. **Release 页面**:
   - 查看性能总结
   - 下载性能报告文件

3. **本地分析**:
   ```bash
   # 下载并解压 artifacts
   # 分析 benchmark_results.json
   python -c "
   import json
   with open('benchmark_results.json') as f:
       data = json.load(f)
   # 进行自定义分析
   "
   ```

### 性能对比

可以对比不同版本间的性能变化：

1. 下载不同版本的 `benchmark_results.json`
2. 使用脚本对比关键指标
3. 生成性能趋势图表

## 故障排除

### 常见问题

1. **测试超时**
   - 检查是否测试规模过大
   - 可能需要调整 `BENCHMARK_TIMEOUT` 环境变量

2. **依赖问题**
   - 确保 `uv.lock` 文件是最新的
   - 检查 `psutil` 依赖是否正确安装

3. **前端构建失败**
   - 检查 `frontend/package.json` 和 `frontend/pnpm-lock.yaml` 文件
   - 确保 Node.js 版本兼容

4. **权限问题**
   - 确保 `GITHUB_TOKEN` 有足够权限
   - 检查 Release 创建权限

### 调试方法

1. **本地测试**:
   ```bash
   # 使用相同参数本地运行
   uv run python benchmark.py --small 200 --medium 2000 --large 8000 --rounds 3
   ```

2. **查看详细日志**:
   - GitHub Actions 页面查看每个步骤的输出
   - 下载 `benchmark_run.log` 查看完整日志

3. **手动触发测试**:
   - 使用较小的参数进行快速测试
   - 逐步增加测试规模定位问题

## 自定义配置

### 修改测试参数

编辑 `.github/workflows/benchmark.yml` 文件：

```yaml
env:
  BENCHMARK_SMALL: '500'    # 修改小规模测试
  BENCHMARK_MEDIUM: '5000'  # 修改中规模测试
  BENCHMARK_LARGE: '20000'  # 修改大规模测试
  BENCHMARK_ROUNDS: '5'     # 修改测试轮数
```

### 添加新的测试场景

可以在 workflow 中添加额外的测试步骤：

```yaml
- name: Custom performance test
  run: |
    uv run python benchmark.py --small 1000 --rounds 1 --output custom_test
```

### 集成其他工具

可以添加性能分析工具：

```yaml
- name: Memory profiling
  run: |
    uv run python -m memory_profiler benchmark.py --small 100
```

## 最佳实践

1. **版本发布**:
   - 每次正式发布前运行性能测试
   - 对比与上一版本的性能差异
   - 在 Release Notes 中包含性能改进说明

2. **性能监控**:
   - 定期查看性能趋势
   - 设置性能回归警报
   - 记录重大性能优化

3. **数据保留**:
   - artifacts 保留 90 天
   - 重要版本的结果可手动备份
   - 建立性能数据历史库

4. **团队协作**:
   - 性能测试结果纳入 Code Review
   - 建立性能标准和目标
   - 定期分析和优化

---

通过这个自动化性能测试系统，可以确保每个版本的性能表现得到量化评估，及时发现性能回归，持续优化系统性能。