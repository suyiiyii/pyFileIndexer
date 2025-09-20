# pyFileIndexer 测试套件

本目录包含 pyFileIndexer 项目的完整测试套件，使用 pytest 框架构建。

## 测试结构

```
tests/
├── __init__.py              # 测试包初始化
├── conftest.py              # pytest 配置和 fixtures
├── test_models.py           # 数据模型测试
├── test_database.py         # 数据库管理器测试
├── test_config.py           # 配置管理测试
├── test_main.py             # 主要业务逻辑测试
├── test_integration.py      # 集成测试
├── utils.py                 # 测试工具函数
├── fixtures/                # 测试数据和工具
│   ├── __init__.py
│   ├── sample_data.py       # 测试样本数据
│   └── test_files/          # 测试文件目录
└── README.md               # 本文件
```

## 测试分类

### 单元测试 (`@pytest.mark.unit`)
- 测试单个函数或方法的功能
- 快速执行，不依赖外部资源
- 包含数据模型、工具函数等测试

### 集成测试 (`@pytest.mark.integration`)
- 测试模块间的协作
- 可能涉及数据库、文件系统操作
- 测试完整的业务流程

### 数据库测试 (`@pytest.mark.database`)
- 涉及数据库操作的测试
- 使用内存数据库确保测试隔离

### 文件系统测试 (`@pytest.mark.filesystem`)
- 需要读写文件的测试
- 使用临时目录确保不影响系统

### 慢速测试 (`@pytest.mark.slow`)
- 执行时间较长的测试
- 性能测试、大数据量测试等

## 快速开始

### 1. 安装测试依赖

```bash
# 安装测试相关依赖
uv sync --group test

# 或者单独安装
pip install pytest pytest-cov pytest-mock pytest-xdist freezegun psutil
```

### 2. 运行测试

```bash
# 运行所有测试
pytest

# 运行特定类型的测试
pytest -m unit          # 只运行单元测试
pytest -m integration   # 只运行集成测试
pytest -m "not slow"    # 跳过慢速测试

# 运行特定文件
pytest tests/test_models.py

# 运行特定测试函数
pytest tests/test_models.py::TestFileHash::test_file_hash_creation

# 并行运行测试
pytest -n auto

# 生成覆盖率报告
pytest --cov=pyFileIndexer --cov-report=html
```

### 3. 使用测试运行脚本

```bash
# 使用项目提供的测试运行脚本
python run_tests.py                    # 运行所有测试
python run_tests.py -t unit           # 只运行单元测试
python run_tests.py -t coverage       # 生成覆盖率报告
python run_tests.py -m test_models    # 运行特定模块
```

## 测试覆盖的功能

### 数据模型测试 (test_models.py)
- ✅ FileHash 和 FileMeta 模型创建
- ✅ 数据库持久化
- ✅ 模型关系和外键约束
- ✅ 重复文件检测逻辑

### 数据库测试 (test_database.py)
- ✅ DatabaseManager 单例模式
- ✅ 数据库初始化和连接
- ✅ CRUD 操作（增删改查）
- ✅ 线程安全性
- ✅ 并发访问控制
- ✅ 错误处理

### 配置测试 (test_config.py)
- ✅ Dynaconf 配置加载
- ✅ 环境变量处理
- ✅ 配置文件优先级
- ✅ 配置验证

### 主要业务逻辑测试 (test_main.py)
- ✅ 文件哈希计算（MD5、SHA1、SHA256）
- ✅ 文件元数据提取
- ✅ 文件扫描逻辑
- ✅ 增量扫描（跳过未修改文件）
- ✅ 工作线程处理
- ✅ 线程安全性
- ✅ 错误处理
- ✅ 性能测试

### 集成测试 (test_integration.py)
- ✅ 端到端扫描流程
- ✅ 数据库持久化
- ✅ 并发扫描
- ✅ 错误恢复
- ✅ 内存使用监控
- ✅ 数据完整性验证

## 测试工具和 Fixtures

### 内置 Fixtures
- `temp_dir`: 临时目录
- `test_db_path`: 测试数据库路径
- `memory_db_manager`: 内存数据库管理器
- `file_db_manager`: 文件数据库管理器
- `test_files`: 各种类型的测试文件
- `mock_settings`: 模拟配置
- `complex_directory_structure`: 复杂目录结构

### 测试工具 (utils.py)
- `TestTimer`: 性能计时器
- `FileCreator`: 测试文件生成器
- `HashVerifier`: 哈希验证工具
- `DatabaseInspector`: 数据库检查工具
- `ThreadSafeCounter`: 线程安全计数器
- `MemoryMonitor`: 内存监控
- `TestEnvironment`: 测试环境管理器

## 性能基准

以下是各类操作的预期性能基准：

| 操作 | 预期时间 | 备注 |
|------|----------|------|
| 小文件哈希计算 (< 1KB) | < 1ms | 单个文件 |
| 中等文件哈希计算 (1MB) | < 100ms | 单个文件 |
| 大文件哈希计算 (10MB) | < 2s | 单个文件 |
| 数据库操作 | < 10ms | 单次操作 |
| 元数据提取 | < 1ms | 单个文件 |

## 测试最佳实践

### 1. 测试隔离
- 每个测试使用独立的临时目录和数据库
- 使用 fixtures 确保测试数据一致性
- 避免测试之间的依赖关系

### 2. 资源清理
- fixtures 自动清理临时文件和数据库
- 使用 context managers 确保资源释放
- 测试结束后验证资源清理

### 3. 错误处理
- 测试正常流程和异常情况
- 验证错误消息和异常类型
- 测试边界条件

### 4. 性能测试
- 使用 `@pytest.mark.slow` 标记耗时测试
- 设置合理的超时时间
- 监控内存使用

### 5. 并发测试
- 测试线程安全性
- 验证数据库锁机制
- 测试竞争条件

## 故障排除

### 常见问题

1. **导入错误**
   ```
   ModuleNotFoundError: No module named 'xxx'
   ```
   - 确保在项目根目录运行测试
   - 检查 PYTHONPATH 设置

2. **数据库锁定**
   ```
   database is locked
   ```
   - 检查是否有未关闭的数据库连接
   - 使用 fixtures 确保连接正确清理

3. **文件权限错误**
   ```
   PermissionError: [Errno 13] Permission denied
   ```
   - 检查临时目录权限
   - 确保测试文件在测试结束后被清理

4. **内存不足**
   ```
   MemoryError
   ```
   - 减少大文件测试的大小
   - 使用 `@pytest.mark.slow` 标记内存密集型测试

### 调试技巧

1. **使用详细输出**
   ```bash
   pytest -v -s
   ```

2. **运行特定测试**
   ```bash
   pytest tests/test_models.py::TestFileHash::test_file_hash_creation -v
   ```

3. **使用 pdb 调试**
   ```bash
   pytest --pdb
   ```

4. **查看覆盖率**
   ```bash
   pytest --cov=pyFileIndexer --cov-report=html
   open htmlcov/index.html
   ```

## 贡献指南

### 添加新测试

1. 确定测试类型（单元、集成等）
2. 选择合适的测试文件或创建新文件
3. 使用适当的 pytest 标记
4. 添加清晰的测试文档字符串
5. 确保测试隔离和资源清理

### 测试命名规范

- 测试文件：`test_<module_name>.py`
- 测试类：`Test<ClassName>`
- 测试方法：`test_<function_name>_<scenario>`

### 标记使用

```python
@pytest.mark.unit              # 单元测试
@pytest.mark.integration       # 集成测试
@pytest.mark.database          # 数据库测试
@pytest.mark.filesystem        # 文件系统测试
@pytest.mark.slow              # 慢速测试
```

## 持续集成

测试套件设计为在 CI/CD 环境中运行：

```yaml
# GitHub Actions 示例
- name: Run tests
  run: |
    pytest -m "not slow" --cov=pyFileIndexer
    pytest -m "slow" --timeout=300
```

## 参考资料

- [pytest 官方文档](https://docs.pytest.org/)
- [pytest-cov 插件](https://pytest-cov.readthedocs.io/)
- [SQLAlchemy 测试指南](https://docs.sqlalchemy.org/en/14/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites)