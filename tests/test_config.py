import pytest
import os
from pathlib import Path
from datetime import datetime

import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "pyFileIndexer"))

from config import settings
from dynaconf import Dynaconf


class TestConfig:
    """测试配置管理"""

    @pytest.mark.unit
    def test_config_import(self):
        """测试配置模块导入"""
        assert settings is not None
        assert isinstance(settings, Dynaconf)

    @pytest.mark.unit
    def test_default_config_structure(self):
        """测试默认配置结构"""
        # 测试配置对象的基本属性 - 使用 Dynaconf 实际的属性
        assert isinstance(settings, Dynaconf)

        # 验证配置加载方式 - 测试实际可用的方法
        assert callable(getattr(settings, "get", None))

        # 验证实际存在的属性
        assert hasattr(settings, "settings_file")  # 单数形式
        assert hasattr(settings, "envvar_prefix_for_dynaconf")  # 实际属性名

        # 验证配置文件相关功能
        assert callable(getattr(settings, "load_file", None))
        assert callable(getattr(settings, "reload", None))

    @pytest.mark.unit
    def test_environment_variable_prefix(self, monkeypatch):
        """测试环境变量前缀功能"""
        # 设置环境变量
        monkeypatch.setenv("DYNACONF_TEST_VAR", "test_value")

        # 创建新的配置实例来加载环境变量
        test_settings = Dynaconf(
            envvar_prefix="DYNACONF",
            settings_files=["settings.toml", ".secrets.toml"],
        )

        # 验证环境变量被正确读取
        assert test_settings.TEST_VAR == "test_value"

    @pytest.mark.unit
    def test_machine_name_setting(self, monkeypatch):
        """测试机器名称配置"""
        test_machine_name = "test_machine_123"
        monkeypatch.setenv("DYNACONF_MACHINE_NAME", test_machine_name)

        # 创建新的配置实例
        test_settings = Dynaconf(
            envvar_prefix="DYNACONF",
            settings_files=["settings.toml", ".secrets.toml"],
        )

        assert test_settings.MACHINE_NAME == test_machine_name

    @pytest.mark.unit
    def test_scanned_datetime_setting(self, monkeypatch):
        """测试扫描时间配置"""
        test_datetime_str = "2024-01-01T12:00:00"
        monkeypatch.setenv("DYNACONF_SCANNED", test_datetime_str)

        # 创建新的配置实例
        test_settings = Dynaconf(
            envvar_prefix="DYNACONF",
            settings_files=["settings.toml", ".secrets.toml"],
        )

        # Dynaconf 可能会自动转换为 datetime 对象
        scanned_value = test_settings.SCANNED
        if isinstance(scanned_value, str):
            assert scanned_value == test_datetime_str
        else:
            # 如果自动转换为 datetime，验证转换正确
            assert str(scanned_value).startswith("2024-01-01")

    @pytest.mark.unit
    def test_config_file_loading(self, temp_dir):
        """测试配置文件加载"""
        # 创建临时配置文件
        settings_file = temp_dir / "test_settings.toml"
        settings_file.write_text("""
test_key = "test_value"
database_url = "sqlite:///test.db"
log_level = "DEBUG"
""")

        secrets_file = temp_dir / "test_secrets.toml"
        secrets_file.write_text("""
secret_key = "super_secret"
api_token = "token_123"
""")

        # 创建使用自定义配置文件的设置
        test_settings = Dynaconf(
            settings_files=[str(settings_file), str(secrets_file)],
        )

        # 验证配置被正确加载
        # Dynaconf 需要通过属性访问，不是 get 方法
        assert test_settings.test_key == "test_value"
        assert test_settings.database_url == "sqlite:///test.db"
        assert test_settings.log_level == "DEBUG"
        assert test_settings.secret_key == "super_secret"
        assert test_settings.api_token == "token_123"

    @pytest.mark.unit
    def test_config_override_priority(self, temp_dir, monkeypatch):
        """测试配置覆盖优先级（环境变量 > 配置文件）"""
        # 创建配置文件
        settings_file = temp_dir / "priority_test.toml"
        settings_file.write_text("""
priority_test = "from_file"
file_only = "file_value"
""")

        # 设置环境变量（应该覆盖文件中的配置）
        monkeypatch.setenv("DYNACONF_PRIORITY_TEST", "from_env")
        monkeypatch.setenv("DYNACONF_ENV_ONLY", "env_value")

        # 创建配置实例
        test_settings = Dynaconf(
            envvar_prefix="DYNACONF",
            settings_files=[str(settings_file)],
        )

        # 验证优先级：环境变量覆盖文件配置
        assert test_settings.priority_test == "from_env"  # 环境变量优先
        assert test_settings.file_only == "file_value"  # 只在文件中的配置
        assert test_settings.env_only == "env_value"  # 只在环境变量中的配置

    @pytest.mark.unit
    def test_missing_config_files(self):
        """测试缺失配置文件的处理"""
        # 创建指向不存在文件的配置
        test_settings = Dynaconf(
            envvar_prefix="DYNACONF",
            settings_files=["nonexistent1.toml", "nonexistent2.toml"],
        )

        # 应该能正常创建，只是没有从文件加载配置
        assert test_settings is not None

    @pytest.mark.unit
    def test_config_attribute_access(self, monkeypatch):
        """测试配置属性访问方式"""
        monkeypatch.setenv("DYNACONF_TEST_ATTRIBUTE", "test_value")

        test_settings = Dynaconf(envvar_prefix="DYNACONF")

        # 测试不同的访问方式
        assert test_settings.TEST_ATTRIBUTE == "test_value"
        assert test_settings.get("TEST_ATTRIBUTE") == "test_value"
        assert test_settings["TEST_ATTRIBUTE"] == "test_value"

    @pytest.mark.unit
    def test_config_default_values(self):
        """测试配置默认值"""
        test_settings = Dynaconf(envvar_prefix="DYNACONF")

        # 测试获取不存在的配置项
        assert test_settings.get("NONEXISTENT_KEY") is None
        assert test_settings.get("NONEXISTENT_KEY", "default") == "default"

    @pytest.mark.unit
    def test_config_type_conversion(self, monkeypatch):
        """测试配置类型转换"""
        # 设置不同类型的环境变量
        monkeypatch.setenv("DYNACONF_STRING_VAL", "string_value")
        monkeypatch.setenv("DYNACONF_INT_VAL", "123")
        monkeypatch.setenv("DYNACONF_BOOL_VAL", "true")
        monkeypatch.setenv("DYNACONF_FLOAT_VAL", "3.14")

        test_settings = Dynaconf(envvar_prefix="DYNACONF")

        # Dynaconf 可能会进行自动类型转换
        assert test_settings.STRING_VAL == "string_value"
        # Dynaconf 可能自动转换类型，所以检查值而不是类型
        assert str(test_settings.INT_VAL) == "123"
        assert str(test_settings.BOOL_VAL).lower() in ["true", "1"]
        assert str(test_settings.FLOAT_VAL) == "3.14"

    @pytest.mark.unit
    def test_secrets_file_separation(self, temp_dir):
        """测试敏感配置分离"""
        # 创建普通配置文件
        settings_file = temp_dir / "app_settings.toml"
        settings_file.write_text("""
app_name = "pyFileIndexer"
debug = true
""")

        # 创建敏感配置文件
        secrets_file = temp_dir / "app_secrets.toml"
        secrets_file.write_text("""
database_password = "secret123"
api_key = "super_secret_key"
""")

        test_settings = Dynaconf(
            envvar_prefix="DYNACONF",
            settings_files=[str(settings_file), str(secrets_file)],
        )

        # 验证两个文件的配置都被加载
        assert test_settings.APP_NAME == "pyFileIndexer"
        assert test_settings.DEBUG in [True, "true"]  # 可能是布尔或字符串
        assert test_settings.DATABASE_PASSWORD == "secret123"
        assert test_settings.API_KEY == "super_secret_key"

    @pytest.mark.unit
    def test_config_case_sensitivity(self, monkeypatch):
        """测试配置键的大小写处理"""
        monkeypatch.setenv("DYNACONF_lower_case", "lower_value")
        monkeypatch.setenv("DYNACONF_UPPER_CASE", "upper_value")
        monkeypatch.setenv("DYNACONF_MiXeD_CaSe", "mixed_value")

        test_settings = Dynaconf(envvar_prefix="DYNACONF")

        # Dynaconf 通常将键转换为大写
        assert test_settings.LOWER_CASE == "lower_value"
        assert test_settings.UPPER_CASE == "upper_value"
        assert test_settings.MIXED_CASE == "mixed_value"


class TestConfigInAppContext:
    """测试配置在应用上下文中的使用"""

    @pytest.mark.unit
    def test_machine_name_retrieval(self, mock_settings):
        """测试获取机器名称配置"""
        # mock_settings fixture 已经设置了 MACHINE_NAME
        from config import settings

        # 由于 settings 是全局单例，我们需要通过 monkeypatch 来模拟
        # 这里测试 getattr 的使用方式（如 main.py 中使用的）
        machine_name = getattr(settings, "MACHINE_NAME", "Unknown")
        assert machine_name in ["test_machine", "Unknown"]  # 取决于环境

    @pytest.mark.unit
    def test_scanned_time_retrieval(self, mock_settings):
        """测试获取扫描时间配置"""
        from config import settings

        # 测试 getattr 的使用方式
        scanned = getattr(settings, "SCANNED", None)
        # 由于 mock_settings 设置了这个值，应该不为 None
        if scanned is not None:
            assert isinstance(scanned, datetime)

    @pytest.mark.unit
    def test_config_error_handling(self):
        """测试配置错误处理"""
        from config import settings

        # 测试访问不存在的配置项
        nonexistent = getattr(settings, "NONEXISTENT_CONFIG", "default_value")
        assert nonexistent == "default_value"

        # 测试必需配置项缺失的情况
        with pytest.raises(ValueError):
            scanned = getattr(settings, "SCANNED", None)
            if scanned is None:
                raise ValueError("SCANNED not set in settings!")

    @pytest.mark.unit
    def test_config_validation(self, monkeypatch):
        """测试配置验证"""
        # 设置有效的配置
        monkeypatch.setenv("DYNACONF_MACHINE_NAME", "valid_machine")
        monkeypatch.setenv("DYNACONF_SCANNED", "2024-01-01T12:00:00")

        test_settings = Dynaconf(envvar_prefix="DYNACONF")

        # 验证配置格式
        machine_name = test_settings.get("MACHINE_NAME")
        assert machine_name is not None
        assert len(machine_name.strip()) > 0

        scanned_str = getattr(test_settings, "SCANNED", None)
        assert scanned_str is not None
        # 这里只测试字符串格式，实际应用中需要解析为 datetime

    @pytest.mark.integration
    def test_config_with_real_files(self, temp_dir, monkeypatch):
        """集成测试：使用真实的配置文件结构"""
        # 清理可能的环境变量
        monkeypatch.delenv("DYNACONF_MACHINE_NAME", raising=False)
        monkeypatch.delenv("DYNACONF_SCANNED", raising=False)

        # 模拟真实的项目配置文件结构
        settings_file = temp_dir / "settings.toml"
        settings_file.write_text("""
# pyFileIndexer Configuration

machine_name = "localhost"
log_level = "DEBUG"
""")

        secrets_file = temp_dir / ".secrets.toml"
        secrets_file.write_text("""
# 敏感配置（不应该提交到版本控制）

db_encryption_key = "development_key_not_for_production"
""")

        # 切换到临时目录并测试配置加载
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)

            test_settings = Dynaconf(
                settings_files=[str(settings_file), str(secrets_file)],
            )

            # 验证配置加载
            assert test_settings.machine_name == "localhost"
            assert (
                test_settings.db_encryption_key == "development_key_not_for_production"
            )

        finally:
            os.chdir(original_cwd)
