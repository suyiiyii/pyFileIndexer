import pytest
import sys
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

# 添加路径
sys.path.insert(0, str(Path(__file__).parent.parent / "web" / "backend"))
sys.path.insert(0, str(Path(__file__).parent.parent / "pyFileIndexer"))

from fastapi.testclient import TestClient
from app import app
from models import FileMeta, FileHash


@pytest.fixture
def client():
    """创建测试客户端"""
    return TestClient(app)


@pytest.fixture
def mock_file_meta():
    """创建模拟文件元数据"""
    import tempfile
    return FileMeta(
        id=1,
        hash_id=1,
        name="test_file.txt",
        path=str(Path(tempfile.gettempdir()) / "test_file.txt"),
        machine="test_machine",
        created=datetime(2024, 1, 1, 12, 0, 0),
        modified=datetime(2024, 1, 1, 12, 0, 0),
        scanned=datetime(2024, 1, 1, 12, 0, 0),
        operation="ADD"
    )


@pytest.fixture
def mock_file_hash():
    """创建模拟文件哈希"""
    return FileHash(
        id=1,
        size=1024,
        md5="d41d8cd98f00b204e9800998ecf8427e",
        sha1="da39a3ee5e6b4b0d3255bfef95601890afd80709",
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


class TestWebAPI:
    """Web API 测试类"""

    def test_root_endpoint(self, client):
        """测试根端点"""
        response = client.get("/")
        assert response.status_code == 200
        # 根路径现在返回前端HTML页面，而不是JSON消息
        assert "<!doctype html>" in response.text.lower()

    def test_health_check(self, client):
        """测试健康检查端点"""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}

    @patch('app.db_manager')
    def test_get_files_success(self, mock_db_manager, client, mock_file_meta, mock_file_hash):
        """测试获取文件列表成功"""
        mock_db_manager.get_files_paginated.return_value = {
            'files': [(mock_file_meta, mock_file_hash)],
            'total': 1,
            'page': 1,
            'per_page': 20,
            'pages': 1
        }

        response = client.get("/api/files")
        assert response.status_code == 200
        data = response.json()

        assert data['total'] == 1
        assert data['page'] == 1
        assert data['per_page'] == 20
        assert len(data['files']) == 1

        file_data = data['files'][0]
        assert file_data['meta']['name'] == "test_file.txt"
        assert file_data['meta']['path'].endswith("test_file.txt")
        assert file_data['hash']['size'] == 1024

    @patch('app.db_manager')
    def test_get_files_with_filters(self, mock_db_manager, client, mock_file_meta, mock_file_hash):
        """测试带过滤器的文件列表查询"""
        mock_db_manager.get_files_paginated.return_value = {
            'files': [(mock_file_meta, mock_file_hash)],
            'total': 1,
            'page': 1,
            'per_page': 20,
            'pages': 1
        }

        response = client.get("/api/files", params={
            "name": "test",
            "machine": "test_machine",
            "min_size": 100,
            "max_size": 2000
        })

        assert response.status_code == 200
        mock_db_manager.get_files_paginated.assert_called_once()

        # 检查调用参数
        call_args = mock_db_manager.get_files_paginated.call_args
        filters = call_args[1]['filters']
        assert filters['name'] == 'test'
        assert filters['machine'] == 'test_machine'
        assert filters['min_size'] == 100
        assert filters['max_size'] == 2000

    @patch('app.db_manager')
    def test_search_files_by_name(self, mock_db_manager, client, mock_file_meta, mock_file_hash):
        """测试按文件名搜索"""
        mock_db_manager.search_files.return_value = [(mock_file_meta, mock_file_hash)]

        response = client.get("/api/search", params={
            "query": "test",
            "search_type": "name"
        })

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]['meta']['name'] == "test_file.txt"

        mock_db_manager.search_files.assert_called_once_with("test", "name")

    @patch('app.db_manager')
    def test_search_files_by_path(self, mock_db_manager, client, mock_file_meta, mock_file_hash):
        """测试按路径搜索"""
        mock_db_manager.search_files.return_value = [(mock_file_meta, mock_file_hash)]
        temp_path = str(Path(tempfile.gettempdir()).parent)  # Get parent of temp directory

        response = client.get("/api/search", params={
            "query": temp_path,
            "search_type": "path"
        })

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert temp_path in data[0]['meta']['path']

        mock_db_manager.search_files.assert_called_once_with(temp_path, "path")

    @patch('app.db_manager')
    def test_search_files_by_hash(self, mock_db_manager, client, mock_file_meta, mock_file_hash):
        """测试按哈希搜索"""
        mock_db_manager.search_files.return_value = [(mock_file_meta, mock_file_hash)]

        response = client.get("/api/search", params={
            "query": "d41d8cd98f00b204e9800998ecf8427e",
            "search_type": "hash"
        })

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]['hash']['md5'] == "d41d8cd98f00b204e9800998ecf8427e"

        mock_db_manager.search_files.assert_called_once_with("d41d8cd98f00b204e9800998ecf8427e", "hash")

    def test_search_files_invalid_type(self, client):
        """测试无效的搜索类型"""
        response = client.get("/api/search", params={
            "query": "test",
            "search_type": "invalid"
        })

        assert response.status_code == 422  # Validation error

    def test_search_files_missing_query(self, client):
        """测试缺少查询参数"""
        response = client.get("/api/search", params={
            "search_type": "name"
        })

        assert response.status_code == 422  # Validation error

    @patch('app.db_manager')
    def test_get_statistics(self, mock_db_manager, client):
        """测试获取统计信息"""
        mock_db_manager.get_statistics.return_value = {
            'total_files': 1000,
            'total_size': 1024000,
            'machine_stats': {'machine1': 500, 'machine2': 500},
            'duplicate_files': 10
        }

        response = client.get("/api/statistics")
        assert response.status_code == 200
        data = response.json()

        assert data['total_files'] == 1000
        assert data['total_size'] == 1024000
        assert data['machine_stats'] == {'machine1': 500, 'machine2': 500}
        assert data['duplicate_files'] == 10

    @patch('app.db_manager')
    def test_get_duplicate_files(self, mock_db_manager, client, mock_file_meta, mock_file_hash):
        """测试获取重复文件"""
        mock_db_manager.find_duplicate_files.return_value = [
            {
                'hash': 'd41d8cd98f00b204e9800998ecf8427e',
                'files': [(mock_file_meta, mock_file_hash), (mock_file_meta, mock_file_hash)]
            }
        ]

        response = client.get("/api/duplicates")
        assert response.status_code == 200
        data = response.json()

        assert len(data['duplicates']) == 1
        duplicate_group = data['duplicates'][0]
        assert duplicate_group['hash'] == 'd41d8cd98f00b204e9800998ecf8427e'
        assert len(duplicate_group['files']) == 2

    @patch('app.db_manager')
    def test_api_error_handling(self, mock_db_manager, client):
        """测试API错误处理"""
        mock_db_manager.get_files_paginated.side_effect = Exception("Database error")

        response = client.get("/api/files")
        assert response.status_code == 500
        assert "Database error" in response.json()['detail']

    def test_pagination_parameters(self, client):
        """测试分页参数验证"""
        # 测试页码小于1
        response = client.get("/api/files", params={"page": 0})
        assert response.status_code == 422

        # 测试每页数量大于100
        response = client.get("/api/files", params={"per_page": 101})
        assert response.status_code == 422

        # 测试负数大小过滤器
        response = client.get("/api/files", params={"min_size": -1})
        assert response.status_code == 422

    @patch('app.db_manager')
    def test_empty_results(self, mock_db_manager, client):
        """测试空结果"""
        mock_db_manager.get_files_paginated.return_value = {
            'files': [],
            'total': 0,
            'page': 1,
            'per_page': 20,
            'pages': 0
        }

        response = client.get("/api/files")
        assert response.status_code == 200
        data = response.json()
        assert data['total'] == 0
        assert len(data['files']) == 0

        mock_db_manager.search_files.return_value = []
        response = client.get("/api/search", params={"query": "nonexistent", "search_type": "name"})
        assert response.status_code == 200
        assert len(response.json()) == 0