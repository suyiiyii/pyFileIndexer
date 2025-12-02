## 目标
- 在执行 `scan` 命令时启动一个轻量 HTTP 端点，实时暴露 Prometheus 风格的指标，便于监控扫描进度、性能与错误情况。
- 指标采集覆盖：目录遍历、文件/压缩包处理、哈希计算、批量写库、队列与线程状态、整体耗时。

## 指标设计
- 计数器（Counter）
  - `pyfileindexer_files_scanned_total{machine}`：已处理文件数（含普通文件与压缩包内部条目）。
  - `pyfileindexer_directories_scanned_total{machine}`：已扫描目录数。
  - `pyfileindexer_archives_scanned_total{machine,type}`：已扫描压缩包数，`type`=zip|tar|rar。
  - `pyfileindexer_archive_entries_total{machine,type}`：压缩包内条目处理数。
  - `pyfileindexer_errors_total{machine,scope}`：错误计数，`scope`=scan_file|scan_archive|worker|dir_iter|db_flush|archive_read|archive_skip。
  - `pyfileindexer_db_writes_total{machine}`：批量写入累计文件记录数。
  - `pyfileindexer_bytes_hashed_total{machine}`：累计参与哈希的字节数（普通文件用 `stat().st_size`，压缩条目用 `entry.size`）。
- 仪表（Gauge）
  - `pyfileindexer_scan_in_progress{machine}`：扫描进行中（1/0）。
  - `pyfileindexer_queue_files_pending{machine}`：文件队列当前长度。
  - `pyfileindexer_workers_running{machine}`：活跃工作线程数。
- 直方图（Histogram）
  - `pyfileindexer_scan_file_duration_seconds{machine}`：单文件处理耗时。
  - `pyfileindexer_db_flush_duration_seconds{machine}`：批量写库耗时。
  - `pyfileindexer_batch_size{machine}`：每次批量写库的批次大小。
- 汇总（Summary，可选）
  - `pyfileindexer_scan_duration_seconds{machine}`：整体扫描耗时（亦可用 Gauge 记录开始时间 + 外部计算）。

## 技术实现
- 依赖选择：使用 `prometheus_client`（线程安全，开销极低）。如未安装，指标模块以 No-Op 方式优雅降级（不影响功能）。
- 启动方式：在 `scan` 子命令启动时可选启用 `--metrics-port`（默认禁用），可选 `--metrics-host`（默认 `0.0.0.0`）。
- 模块化：新增 `pyFileIndexer/metrics.py` 封装所有指标定义与更新 API：
  - `init(machine_name: str)`、`start_http_server(port: int, host: str)`。
  - 方法：`inc_files(...)`、`inc_dirs()`、`inc_archives(type)`、`inc_archive_entries(type, n)`、`inc_errors(scope)`、`inc_db_writes(n)`、`inc_bytes(n)`、`observe_file_duration(sec)`、`observe_db_flush(sec, batch_size)`、`set_queue_size(n)`、`set_workers(n)`、`set_scan_in_progress(0|1)`。
  - 若 `prometheus_client` 缺失，以上方法均为 no-op。
- 并发与性能：`prometheus_client` 的 Counter/Gauge 在多线程下安全；更新点选择在已有日志/进度钩子处，避免额外 IO。

## 改动点位
- `pyFileIndexer/main.py`
  - CLI 增加参数：`--metrics-port`、`--metrics-host`（在 `__main__` 解析处 468+）。
  - 在 `scan` 入口启用指标并置位状态：`scan(path)` 开始前 `set_scan_in_progress(1)`，结束后 `set_scan_in_progress(0)`（359）。
  - 目录遍历：`scan_directory(...)` 每处理一个目录后 `pyfileindexer_directories_scanned_total++`（327）。
  - 文件队列与线程：
    - 刷新线程 `_force_refresh` 中周期同步 `queue_files_pending=file_queue.qsize()` 与 `workers_running=len(workers)`（391-404、405-416）。
    - `scan_file_worker(...)` 成功处理后 `files_scanned_total++`；异常分支 `errors_total{scope=worker}++`（284）。
  - 单文件处理：`scan_file(file)` 完成哈希后 `bytes_hashed_total+=file_stat.st_size`；异常分支 `errors_total{scope=scan_file}++`（187-213）。
  - 压缩包：`scan_archive_file(...)`
    - 入口 `archives_scanned_total{type}++`；超过大小或无法创建扫描器时 `errors_total{scope=archive_skip}++`（215-233）。
    - 每个条目成功入批后 `archive_entries_total{type}++` 与 `bytes_hashed_total+=entry.size`；条目读取/处理异常 `errors_total{scope=archive_read}++`（237-278）。
  - 批处理：`BatchProcessor._flush_batch(...)`
    - 记录 flush 开始/结束时间，更新 `db_flush_duration_seconds` 与 `batch_size`，同时 `db_writes_total += len(batch_data)`；异常 `errors_total{scope=db_flush}++`（159-171）。
  - 单文件耗时：在 `scan_file_worker` 包裹计时后 `observe_file_duration(...)`。
- `pyFileIndexer/archive_scanner.py`
  - 无需强耦合修改；错误/跳过已在 `main.py` 侧按结果聚合更新指标。若需要细粒度区分，可在各 `scan_entries()` 内部读取错误处调用 `metrics.inc_errors('archive_read')`（41、160、208、263）。
- 新增 `pyFileIndexer/metrics.py`
  - 定义所有指标与 API；提供 No-Op 兼容；统一接入点由 `main.py` 调用。

## 使用示例
- 运行：`python pyFileIndexer/main.py scan /data --metrics-port 9090 --metrics-host 0.0.0.0`
- 检查：`curl http://localhost:9090/metrics` 可看到上述指标；Grafana/Prometheus 用 `rate(pyfileindexer_files_scanned_total[1m])` 观察吞吐。
- 依赖：如未安装，建议 `pip install prometheus-client`；未安装时指标静默禁用并在日志中提示。

## 验证与回归
- 本地用小目录与包含 zip/tar/rar 的样例进行扫描，观察指标随进度变化。
- 人为制造错误（不可读文件、数据库写入异常）验证 `errors_total{scope=*}` 计数增加。
- 压力测试长时间运行，确认端点稳定、线程安全与低开销（Counters/Gauges 更新在微秒级）。

## 兼容性与安全
- 指标端点仅提供只读监控；不暴露敏感数据，不记录具体路径内容。
- 标签控制在低基数范围（`machine` 固定、`type` 为有限集合）。
- 端点可绑定 `127.0.0.1` 以避免外部暴露。

## 后续扩展（可选）
- 增加 `pyfileindexer_bytes_per_second` 导出为速率指标（外部用 `rate()` 即可）。
- 在 `serve` 模式合并展示 DB 浏览与指标端点（共享注册器）。
- 导出进度估算：`pbar.total` 与已完成数的比值（通过 Gauge）。