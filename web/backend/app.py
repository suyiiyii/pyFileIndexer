import sys
from pathlib import Path

# 添加 pyFileIndexer 模块到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "pyFileIndexer"))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import Optional

from database import db_manager
from web.backend.models.responses import (
    PaginatedFilesResponse,
    StatisticsResponse,
    DuplicateFilesResponse,
    SearchFiltersRequest,
    FileWithHashResponse,
    FileMetaResponse,
    FileHashResponse,
    DuplicateFileGroup
)

app = FastAPI(
    title="pyFileIndexer API",
    description="File indexing and search API",
    version="1.0.0"
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],  # React 开发服务器
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def convert_db_record_to_response(file_meta, file_hash) -> FileWithHashResponse:
    """将数据库记录转换为响应模型"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        # 安全地访问file_meta属性，提供默认值
        meta_response = FileMetaResponse(
            id=getattr(file_meta, 'id', None),
            hash_id=getattr(file_meta, 'hash_id', None),
            name=getattr(file_meta, 'name', ''),
            path=getattr(file_meta, 'path', ''),
            machine=getattr(file_meta, 'machine', 'unknown'),
            created=getattr(file_meta, 'created', '1970-01-01T00:00:00'),
            modified=getattr(file_meta, 'modified', '1970-01-01T00:00:00'),
            scanned=getattr(file_meta, 'scanned', '1970-01-01T00:00:00'),
            operation=getattr(file_meta, 'operation', 'ADD')
        )

        hash_response = None
        if file_hash:
            try:
                hash_response = FileHashResponse(
                    id=getattr(file_hash, 'id', None),
                    size=getattr(file_hash, 'size', 0),
                    md5=getattr(file_hash, 'md5', ''),
                    sha1=getattr(file_hash, 'sha1', ''),
                    sha256=getattr(file_hash, 'sha256', '')
                )
            except Exception as e:
                logger.error(f"Error processing file_hash: {e}")
                hash_response = None

        return FileWithHashResponse(meta=meta_response, hash=hash_response)

    except Exception as e:
        logger.error(f"Error converting database record to response: {e}")
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
                operation="ERROR"
            ),
            hash=None
        )


# 根路径由通配符路由处理，返回前端页面


@app.get("/api/files", response_model=PaginatedFilesResponse)
async def get_files(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    name: Optional[str] = Query(None),
    path: Optional[str] = Query(None),
    machine: Optional[str] = Query(None),
    min_size: Optional[int] = Query(None, ge=0),
    max_size: Optional[int] = Query(None, ge=0),
    hash_value: Optional[str] = Query(None)
):
    """获取文件列表，支持分页和过滤"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        logger.info(f"Getting files: page={page}, per_page={per_page}")

        filters = {}
        if name:
            filters['name'] = name
        if path:
            filters['path'] = path
        if machine:
            filters['machine'] = machine
        if min_size is not None:
            filters['min_size'] = min_size
        if max_size is not None:
            filters['max_size'] = max_size
        if hash_value:
            filters['hash_value'] = hash_value

        logger.debug(f"Filters applied: {filters}")

        result = db_manager.get_files_paginated(
            page=page,
            per_page=per_page,
            filters=filters if filters else None
        )

        logger.info(f"Database returned {len(result['files'])} files, total={result['total']}")

        files = []
        for file_meta, file_hash in result['files']:
            try:
                file_response = convert_db_record_to_response(file_meta, file_hash)
                files.append(file_response)
            except Exception as e:
                logger.error(f"Error converting file record: {e}")
                continue

        response = PaginatedFilesResponse(
            files=files,
            total=result['total'],
            page=result['page'],
            per_page=result['per_page'],
            pages=result['pages']
        )

        logger.info(f"Returning {len(files)} files in response")
        return response

    except Exception as e:
        logger.error(f"Error in get_files endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/api/search", response_model=list[FileWithHashResponse])
async def search_files(
    query: str = Query(..., description="搜索关键词"),
    search_type: str = Query("name", regex="^(name|path|hash)$", description="搜索类型")
):
    """搜索文件"""
    try:
        results = db_manager.search_files(query, search_type)

        return [
            convert_db_record_to_response(file_meta, file_hash)
            for file_meta, file_hash in results
        ]
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
async def get_duplicate_files():
    """获取重复文件"""
    try:
        duplicates_data = db_manager.find_duplicate_files()

        duplicates = []
        for dup_group in duplicates_data:
            files = [
                convert_db_record_to_response(file_meta, file_hash)
                for file_meta, file_hash in dup_group['files']
            ]
            duplicates.append(DuplicateFileGroup(
                hash=dup_group['hash'],
                files=files
            ))

        return DuplicateFilesResponse(duplicates=duplicates)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy"}


# 配置静态文件服务
frontend_dist_path = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist_path.exists():
    # 服务静态文件
    app.mount("/static", StaticFiles(directory=str(frontend_dist_path / "assets")), name="static")

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)