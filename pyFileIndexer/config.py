from dynaconf import Dynaconf

settings = Dynaconf(
    envvar_prefix="DYNACONF",
    settings_files=["settings.toml", ".secrets.toml"],
)

# `envvar_prefix` = export envvars with `export DYNACONF_FOO=bar`.
# `settings_files` = Load these files in the order.


def validate_settings():
    """验证关键配置项，提供有用的错误信息。"""
    warnings = []

    machine_name = getattr(settings, "MACHINE_NAME", None)
    if not machine_name:
        warnings.append("MACHINE_NAME 未设置，将使用 'localhost'")

    scanned = getattr(settings, "SCANNED", None)
    if not scanned:
        warnings.append("SCANNED 未设置，将使用当前时间")

    # Archive scanning configuration validation
    scan_archives = getattr(settings, "SCAN_ARCHIVES", True)
    if scan_archives:
        max_archive_size = getattr(settings, "MAX_ARCHIVE_SIZE", 524288000)
        if max_archive_size < 0:
            warnings.append("MAX_ARCHIVE_SIZE 应该为正数")

        max_archive_file_size = getattr(settings, "MAX_ARCHIVE_FILE_SIZE", 104857600)
        if max_archive_file_size < 0:
            warnings.append("MAX_ARCHIVE_FILE_SIZE 应该为正数")

    return warnings
