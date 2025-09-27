import React, { useState, useEffect } from 'react';
import { Table, Card, Input, InputNumber, Button, Tag, message } from 'antd';
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { fileAPI } from '../services/api';
import { FileWithHash } from '../types/api';

// const { Option } = Select;

interface FileListProps {
  title?: string;
}

const FileList: React.FC<FileListProps> = ({ title = "文件列表" }) => {
  const [files, setFiles] = useState<FileWithHash[]>([]);
  const [loading, setLoading] = useState(false);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 20,
    total: 0,
  });

  // 搜索参数
  const [searchParams, setSearchParams] = useState({
    name: '',
    path: '',
    machine: '',
    min_size: undefined as number | undefined,
    max_size: undefined as number | undefined,
    hash_value: '',
  });

  const formatFileSize = (bytes: number | undefined): string => {
    if (!bytes) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let size = bytes;
    let unitIndex = 0;

    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex++;
    }

    return `${size.toFixed(unitIndex === 0 ? 0 : 2)} ${units[unitIndex]}`;
  };

  const formatDate = (dateString: string): string => {
    return new Date(dateString).toLocaleString('zh-CN');
  };

  const columns: ColumnsType<FileWithHash> = [
    {
      title: '文件名',
      dataIndex: ['meta', 'name'],
      key: 'name',
      ellipsis: true,
      width: 200,
    },
    {
      title: '路径',
      dataIndex: ['meta', 'path'],
      key: 'path',
      ellipsis: true,
      width: 300,
    },
    {
      title: '大小',
      key: 'size',
      width: 100,
      render: (_, record) => formatFileSize(record.hash?.size),
    },
    {
      title: '机器',
      dataIndex: ['meta', 'machine'],
      key: 'machine',
      width: 120,
      render: (machine) => <Tag color="blue">{machine}</Tag>,
    },
    {
      title: '修改时间',
      dataIndex: ['meta', 'modified'],
      key: 'modified',
      width: 160,
      render: (date) => formatDate(date),
    },
    {
      title: '操作类型',
      dataIndex: ['meta', 'operation'],
      key: 'operation',
      width: 100,
      render: (operation) => (
        <Tag color={operation === 'ADD' ? 'green' : 'orange'}>
          {operation}
        </Tag>
      ),
    },
    {
      title: 'MD5',
      dataIndex: ['hash', 'md5'],
      key: 'md5',
      width: 200,
      ellipsis: true,
      render: (md5) => md5 ? <code style={{ fontSize: '12px' }}>{md5}</code> : '-',
    },
  ];

  const fetchFiles = async (page = 1, pageSize = 20) => {
    setLoading(true);
    try {
      const params = {
        page,
        per_page: pageSize,
        ...Object.fromEntries(
          Object.entries(searchParams).filter(([, value]) =>
            value !== '' && value !== undefined
          )
        ),
      };

      const response = await fileAPI.getFiles(params);
      setFiles(response.files);
      setPagination({
        current: response.page,
        pageSize: response.per_page,
        total: response.total,
      });
    } catch (error) {
      message.error('获取文件列表失败');
      console.error('Error fetching files:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFiles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSearch = () => {
    fetchFiles(1, pagination.pageSize);
  };

  const handleReset = () => {
    setSearchParams({
      name: '',
      path: '',
      machine: '',
      min_size: undefined,
      max_size: undefined,
      hash_value: '',
    });
    setTimeout(() => fetchFiles(1, pagination.pageSize), 0);
  };

  const handleTableChange = (paginationConfig: { current?: number; pageSize?: number }) => {
    fetchFiles(paginationConfig.current || 1, paginationConfig.pageSize || 20);
  };

  return (
    <Card title={title} className="shadow-sm">
      {/* 搜索区域 */}
      <div className="mb-6 p-4 bg-gray-50 rounded-lg">
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Input
              placeholder="文件名"
              value={searchParams.name}
              onChange={(e) => setSearchParams({ ...searchParams, name: e.target.value })}
              className="w-full"
            />
            <Input
              placeholder="路径"
              value={searchParams.path}
              onChange={(e) => setSearchParams({ ...searchParams, path: e.target.value })}
              className="w-full md:col-span-2"
            />
            <Input
              placeholder="机器名"
              value={searchParams.machine}
              onChange={(e) => setSearchParams({ ...searchParams, machine: e.target.value })}
              className="w-full"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 items-center">
            <span className="text-sm font-medium text-gray-700">文件大小：</span>
            <InputNumber
              placeholder="最小大小(字节)"
              value={searchParams.min_size}
              onChange={(value) => setSearchParams({ ...searchParams, min_size: value || undefined })}
              className="w-full"
            />
            <span className="text-sm text-gray-500 text-center">至</span>
            <InputNumber
              placeholder="最大大小(字节)"
              value={searchParams.max_size}
              onChange={(value) => setSearchParams({ ...searchParams, max_size: value || undefined })}
              className="w-full"
            />
            <Input
              placeholder="哈希值(MD5/SHA1/SHA256)"
              value={searchParams.hash_value}
              onChange={(e) => setSearchParams({ ...searchParams, hash_value: e.target.value })}
              className="w-full"
            />
          </div>

          <div className="flex flex-wrap gap-3">
            <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>
              搜索
            </Button>
            <Button icon={<ReloadOutlined />} onClick={handleReset}>
              重置
            </Button>
          </div>
        </div>
      </div>

      {/* 文件表格 */}
      <div className="overflow-hidden rounded-lg border border-gray-200">
        <div className="overflow-x-auto">
          <Table
            columns={columns}
            dataSource={files}
            rowKey={(record) => `${record.meta.id || record.meta.path}`}
            loading={loading}
            pagination={{
              ...pagination,
              showSizeChanger: true,
              showQuickJumper: true,
              showTotal: (total, range) => `第 ${range[0]}-${range[1]} 条，共 ${total} 条`,
              pageSizeOptions: ['10', '20', '50', '100'],
            }}
            onChange={handleTableChange}
            scroll={{ x: 1400 }}
            size="small"
            className="min-w-full"
          />
        </div>
      </div>
    </Card>
  );
};

export default FileList;