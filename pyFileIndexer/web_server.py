import os
import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def start_web_server(db_path: str, host: str, port: int):
    """启动集成的Web服务器"""

    # 检查数据库文件是否存在
    if not os.path.exists(db_path):
        logger.error(f"数据库文件不存在: {db_path}")
        logger.info("请先运行扫描命令创建数据库：")
        logger.info(f"  python main.py <scan_path> --db_path {db_path}")
        sys.exit(1)

    # 检查前端构建文件是否存在
    project_root = Path(__file__).parent.parent
    frontend_dist = project_root / "web" / "frontend" / "dist"

    if not frontend_dist.exists() or not (frontend_dist / "index.html").exists():
        logger.error("前端构建文件不存在，正在尝试构建前端...")

        # 尝试构建前端
        frontend_path = project_root / "web" / "frontend"
        if not frontend_path.exists():
            logger.error("前端项目目录不存在")
            sys.exit(1)

        # 检查是否安装了 npm/node
        try:
            import subprocess
            result = subprocess.run(["npm", "--version"], capture_output=True, text=True)
            if result.returncode != 0:
                logger.error("npm 未安装，无法构建前端")
                logger.info("请手动构建前端：")
                logger.info(f"  cd {frontend_path}")
                logger.info("  npm install")
                logger.info("  npm run build")
                sys.exit(1)
        except FileNotFoundError:
            logger.error("npm 未找到，无法构建前端")
            logger.info("请确保已安装 Node.js 和 npm")
            sys.exit(1)

        # 尝试自动构建前端
        try:
            logger.info("正在安装前端依赖...")
            result = subprocess.run(
                ["npm", "install"],
                cwd=frontend_path,
                capture_output=True,
                text=True,
                timeout=300  # 5分钟超时
            )
            if result.returncode != 0:
                logger.error(f"npm install 失败: {result.stderr}")
                sys.exit(1)

            logger.info("正在构建前端...")
            result = subprocess.run(
                ["npm", "run", "build"],
                cwd=frontend_path,
                capture_output=True,
                text=True,
                timeout=180  # 3分钟超时
            )
            if result.returncode != 0:
                logger.error(f"npm run build 失败: {result.stderr}")
                sys.exit(1)

            logger.info("前端构建完成")

        except subprocess.TimeoutExpired:
            logger.error("前端构建超时")
            sys.exit(1)
        except Exception as e:
            logger.error(f"前端构建失败: {e}")
            logger.info("请手动构建前端：")
            logger.info(f"  cd {frontend_path}")
            logger.info("  npm install")
            logger.info("  npm run build")
            sys.exit(1)

    # 导入并启动 FastAPI 应用
    try:
        # 添加 web/backend 到 Python 路径
        backend_path = project_root / "web" / "backend"
        sys.path.insert(0, str(backend_path))
        sys.path.insert(0, str(project_root))

        from app import app
        import uvicorn

        logger.info(f"启动 Web 服务器...")
        logger.info(f"数据库路径: {db_path}")
        logger.info(f"服务地址: http://{host}:{port}")
        logger.info("按 Ctrl+C 停止服务器")

        # 启动服务器
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=True
        )

    except ImportError as e:
        logger.error(f"导入 Web 应用失败: {e}")
        logger.error("请确保已安装 FastAPI 相关依赖")
        sys.exit(1)
    except Exception as e:
        logger.error(f"启动 Web 服务器失败: {e}")
        sys.exit(1)