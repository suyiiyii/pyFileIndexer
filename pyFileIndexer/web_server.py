import os
import sys
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

from .database import db_manager
from .dto import FileWithHashDTO
from .web_models import (
    PaginatedFilesResponse,
    StatisticsResponse,
    DuplicateFilesResponse,
    FileWithHashResponse,
    FileMetaResponse,
    FileHashResponse,
    DuplicateFileGroup,
    TreeDataResponse,
    TreeFileInfo,
)

logger = logging.getLogger(__name__)


def convert_dto_to_response(dto: FileWithHashDTO) -> FileWithHashResponse:
    """将 DTO 转换为响应模型"""
    try:
        # 直接访问 DTO 属性
        meta_response = FileMetaResponse(
            id=dto.meta.id,
            hash_id=dto.meta.hash_id,
            name=dto.meta.name,
            path=dto.meta.path,
            machine=dto.meta.machine,
            created=dto.meta.created,
            modified=dto.meta.modified,
            scanned=dto.meta.scanned,
            operation=dto.meta.operation,
        )

        hash_response = None
        if dto.hash:
            hash_response = FileHashResponse(
                id=dto.hash.id,
                size=dto.hash.size,
                md5=dto.hash.md5,
                sha1=dto.hash.sha1,
                sha256=dto.hash.sha256,
            )

        return FileWithHashResponse(meta=meta_response, hash=hash_response)

    except Exception as e:
        logger.error(f"Error converting DTO to response: {e}")
        # 返回一个最基本的响应，避免完全失败
        return FileWithHashResponse(
            meta=FileMetaResponse(
                id=None,
                hash_id=None,
                name="Error loading file",
                path="",
                machine="unknown",
                created="1970-01-01T00:00:00",
                modified="1970-01-01T00:00:00",
                scanned="1970-01-01T00:00:00",
                operation="ERROR",
            ),
            hash=None,
        )


def create_app() -> FastAPI:
    """创建FastAPI应用"""
    app = FastAPI(
        title="pyFileIndexer API",
        description="File indexing and search API",
        version="1.0.0",
    )

    # 配置 CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:5173",
        ],  # React 开发服务器
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/files", response_model=PaginatedFilesResponse)
    async def get_files(
        page: int = Query(1, ge=1),
        per_page: int = Query(20, ge=1, le=100),
        name: Optional[str] = Query(None),
        path: Optional[str] = Query(None),
        machine: Optional[str] = Query(None),
        min_size: Optional[int] = Query(None, ge=0),
        max_size: Optional[int] = Query(None, ge=0),
        hash_value: Optional[str] = Query(None),
    ):
        """获取文件列表，支持分页和过滤"""
        try:
            logger.info(f"Getting files: page={page}, per_page={per_page}")

            filters = {}
            if name:
                filters["name"] = name
            if path:
                filters["path"] = path
            if machine:
                filters["machine"] = machine
            if min_size is not None:
                filters["min_size"] = min_size
            if max_size is not None:
                filters["max_size"] = max_size
            if hash_value:
                filters["hash_value"] = hash_value

            logger.debug(f"Filters applied: {filters}")

            result = db_manager.get_files_paginated(
                page=page, per_page=per_page, filters=filters if filters else None
            )

            logger.info(
                f"Database returned {len(result['files'])} files, total={result['total']}"
            )

            files = []
            for dto in result["files"]:
                try:
                    file_response = convert_dto_to_response(dto)
                    files.append(file_response)
                except Exception as e:
                    logger.error(f"Error converting file record: {e}")
                    continue

            response = PaginatedFilesResponse(
                files=files,
                total=result["total"],
                page=result["page"],
                per_page=result["per_page"],
                pages=result["pages"],
            )

            logger.info(f"Returning {len(files)} files in response")
            return response

        except Exception as e:
            logger.error(f"Error in get_files endpoint: {e}")
            raise HTTPException(
                status_code=500, detail=f"Internal server error: {str(e)}"
            )

    @app.get("/api/search", response_model=list[FileWithHashResponse])
    async def search_files(
        query: str = Query(..., description="搜索关键词"),
        search_type: str = Query(
            "name", regex="^(name|path|hash)$", description="搜索类型"
        ),
    ):
        """搜索文件"""
        try:
            results = db_manager.search_files(query, search_type)

            return [convert_dto_to_response(dto) for dto in results]
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/statistics", response_model=StatisticsResponse)
    async def get_statistics():
        """获取统计信息"""
        try:
            stats = db_manager.get_statistics()
            return StatisticsResponse(**stats)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/duplicates", response_model=DuplicateFilesResponse)
    async def get_duplicate_files(
        page: int = Query(1, ge=1, description="页码"),
        per_page: int = Query(20, ge=1, le=100, description="每页数量"),
        min_size: int = Query(
            1048576, ge=0, description="最小文件大小（字节），默认1MB"
        ),
        min_count: int = Query(2, ge=2, description="最小重复数量"),
        sort_by: str = Query(
            "count_desc",
            regex="^(count_desc|count_asc|size_desc|size_asc)$",
            description="排序方式: count_desc, count_asc, size_desc, size_asc",
        ),
    ):
        """获取重复文件，支持分页、过滤和排序"""
        try:
            logger.info(
                f"Getting duplicate files: page={page}, per_page={per_page}, "
                f"min_size={min_size}, min_count={min_count}, sort_by={sort_by}"
            )
            result = db_manager.find_duplicate_files(
                page=page,
                per_page=per_page,
                min_size=min_size,
                min_count=min_count,
                sort_by=sort_by,
            )
            logger.info(
                f"Found {result['total_groups']} total groups, "
                f"returning {len(result['duplicates'])} groups for page {page}"
            )

            duplicates = []
            for dup_group in result["duplicates"]:
                try:
                    files = [convert_dto_to_response(dto) for dto in dup_group["files"]]
                    duplicates.append(
                        DuplicateFileGroup(hash=dup_group["hash"], files=files)
                    )
                except Exception as group_error:
                    logger.error(
                        f"Error processing duplicate group: {group_error}",
                        exc_info=True,
                    )
                    continue

            return DuplicateFilesResponse(
                duplicates=duplicates,
                total_groups=result["total_groups"],
                total_files=result["total_files"],
                page=result["page"],
                per_page=result["per_page"],
                pages=result["pages"],
            )
        except Exception as e:
            logger.error(f"Error in get_duplicate_files endpoint: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, detail=f"Internal server error: {str(e)}"
            )

    @app.get("/health")
    async def health_check():
        """健康检查端点"""
        return {"status": "healthy"}

    @app.get("/api/tree", response_model=TreeDataResponse)
    async def get_tree_data(path: str = Query("")):
        """获取树形结构数据

        Args:
            path: 路径，格式为 /machine/path1/path2 或空字符串，空字符串返回所有机器
        """
        try:
            logger.info(f"Getting tree data for path: {path}")
            result = db_manager.get_tree_data(path)

            # 转换文件数据
            files = []
            for dto in result["files"]:
                hash_response = None
                if dto.hash:
                    hash_response = FileHashResponse(
                        id=dto.hash.id,
                        size=dto.hash.size,
                        md5=dto.hash.md5,
                        sha1=dto.hash.sha1,
                        sha256=dto.hash.sha256,
                    )

                file_info = TreeFileInfo(
                    name=dto.meta.name,
                    size=dto.hash.size if dto.hash else 0,
                    modified=dto.meta.modified,
                    hash=hash_response,
                )
                files.append(file_info)

            return TreeDataResponse(
                current_path=result["current_path"],
                directories=result["directories"],
                files=files,
            )
        except Exception as e:
            logger.error(f"Error in get_tree_data endpoint: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, detail=f"Internal server error: {str(e)}"
            )

    # 配置静态文件服务
    project_root = Path(__file__).parent.parent
    frontend_dist_path = project_root / "frontend" / "dist"

    if frontend_dist_path.exists():
        # 服务静态文件
        app.mount(
            "/static",
            StaticFiles(directory=str(frontend_dist_path / "assets")),
            name="static",
        )

        # 服务前端应用（所有非API路径）
        @app.get("/{path:path}")
        async def serve_frontend(path: str):
            """服务前端应用，对于非API路径返回index.html"""
            # 如果是API路径，返回404
            if path.startswith("api/"):
                raise HTTPException(status_code=404, detail="API endpoint not found")

            # 检查是否是静态文件
            file_path = frontend_dist_path / path
            if file_path.is_file():
                return FileResponse(file_path)

            # 对于其他所有路径，返回 index.html（SPA路由）
            index_path = frontend_dist_path / "index.html"
            if index_path.exists():
                return FileResponse(index_path)
            else:
                raise HTTPException(status_code=404, detail="Frontend not built")

    return app


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
    frontend_dist = project_root / "frontend" / "dist"

    if not frontend_dist.exists() or not (frontend_dist / "index.html").exists():
        logger.error("前端构建文件不存在")
        logger.info("请手动构建前端：")
        frontend_path = project_root / "frontend"
        logger.info(f"  cd {frontend_path}")
        logger.info("  pnpm install")
        logger.info("  pnpm run build")
        sys.exit(1)

    try:
        app = create_app()

        logger.info("启动 Web 服务器...")
        logger.info(f"数据库路径: {db_path}")
        logger.info(f"服务地址: http://{host}:{port}")
        logger.info("按 Ctrl+C 停止服务器")

        # 启动服务器
        uvicorn.run(app, host=host, port=port, log_level="info", access_log=True)

    except Exception as e:
        logger.error(f"启动 Web 服务器失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # 用于开发测试
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)
