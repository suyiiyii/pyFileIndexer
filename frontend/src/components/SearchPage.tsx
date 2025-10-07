import React, { useState } from 'react';
import { Card, Input, Select, Button, Table, Tag, message } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { fileAPI } from '../services/api';
import { FileWithHash } from '../types/api';
import EllipsisWithTooltip from './EllipsisWithTooltip';

const { Option } = Select;

const SearchPage: React.FC = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchType, setSearchType] = useState<'name' | 'path' | 'hash'>('name');
  const [searchResults, setSearchResults] = useState<FileWithHash[]>([]);
  const [loading, setLoading] = useState(false);

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
      width: 200,
      render: (name) => {
        let content = name;
        if (searchType === 'name' && searchQuery) {
          const index = name.toLowerCase().indexOf(searchQuery.toLowerCase());
          if (index >= 0) {
            const beforeStr = name.substring(0, index);
            const matchStr = name.substring(index, index + searchQuery.length);
            const afterStr = name.substring(index + searchQuery.length);
            content = (
              <span>
                {beforeStr}
                <mark style={{ backgroundColor: '#ffe58f', padding: 0 }}>{matchStr}</mark>
                {afterStr}
              </span>
            );
          }
        }
        return <EllipsisWithTooltip text={name} showCopyIcon>{content}</EllipsisWithTooltip>;
      },
    },
    {
      title: '路径',
      dataIndex: ['meta', 'path'],
      key: 'path',
      width: 350,
      render: (path) => {
        let content = path;
        if (searchType === 'path' && searchQuery) {
          const index = path.toLowerCase().indexOf(searchQuery.toLowerCase());
          if (index >= 0) {
            const beforeStr = path.substring(0, index);
            const matchStr = path.substring(index, index + searchQuery.length);
            const afterStr = path.substring(index + searchQuery.length);
            content = (
              <span>
                {beforeStr}
                <mark style={{ backgroundColor: '#ffe58f', padding: 0 }}>{matchStr}</mark>
                {afterStr}
              </span>
            );
          }
        }
        return <EllipsisWithTooltip text={path} showCopyIcon>{content}</EllipsisWithTooltip>;
      },
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
      render: (md5) => {
        if (!md5) return '-';
        let content = <code style={{ fontSize: '12px' }}>{md5}</code>;
        if (searchType === 'hash' && searchQuery && md5.includes(searchQuery)) {
          const index = md5.indexOf(searchQuery);
          const beforeStr = md5.substring(0, index);
          const matchStr = md5.substring(index, index + searchQuery.length);
          const afterStr = md5.substring(index + searchQuery.length);
          content = (
            <code style={{ fontSize: '12px' }}>
              {beforeStr}
              <mark style={{ backgroundColor: '#ffe58f', padding: 0 }}>{matchStr}</mark>
              {afterStr}
            </code>
          );
        }
        return <EllipsisWithTooltip text={md5} showCopyIcon>{content}</EllipsisWithTooltip>;
      },
    },
    {
      title: 'SHA1',
      dataIndex: ['hash', 'sha1'],
      key: 'sha1',
      width: 200,
      render: (sha1) => {
        if (!sha1) return '-';
        let content = <code style={{ fontSize: '12px' }}>{sha1}</code>;
        if (searchType === 'hash' && searchQuery && sha1.includes(searchQuery)) {
          const index = sha1.indexOf(searchQuery);
          const beforeStr = sha1.substring(0, index);
          const matchStr = sha1.substring(index, index + searchQuery.length);
          const afterStr = sha1.substring(index + searchQuery.length);
          content = (
            <code style={{ fontSize: '12px' }}>
              {beforeStr}
              <mark style={{ backgroundColor: '#ffe58f', padding: 0 }}>{matchStr}</mark>
              {afterStr}
            </code>
          );
        }
        return <EllipsisWithTooltip text={sha1} showCopyIcon>{content}</EllipsisWithTooltip>;
      },
    },
    {
      title: 'SHA256',
      dataIndex: ['hash', 'sha256'],
      key: 'sha256',
      width: 200,
      render: (sha256) => {
        if (!sha256) return '-';
        let content = <code style={{ fontSize: '12px' }}>{sha256}</code>;
        if (searchType === 'hash' && searchQuery && sha256.includes(searchQuery)) {
          const index = sha256.indexOf(searchQuery);
          const beforeStr = sha256.substring(0, index);
          const matchStr = sha256.substring(index, index + searchQuery.length);
          const afterStr = sha256.substring(index + searchQuery.length);
          content = (
            <code style={{ fontSize: '12px' }}>
              {beforeStr}
              <mark style={{ backgroundColor: '#ffe58f', padding: 0 }}>{matchStr}</mark>
              {afterStr}
            </code>
          );
        }
        return <EllipsisWithTooltip text={sha256} showCopyIcon>{content}</EllipsisWithTooltip>;
      },
    },
  ];

  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      message.warning('请输入搜索关键词');
      return;
    }

    setLoading(true);
    try {
      const results = await fileAPI.searchFiles(searchQuery, searchType);
      setSearchResults(results);
      message.success(`找到 ${results.length} 个匹配的文件`);
    } catch (error) {
      message.error('搜索失败');
      console.error('Search error:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  const getSearchTypeText = () => {
    switch (searchType) {
      case 'name':
        return '文件名';
      case 'path':
        return '路径';
      case 'hash':
        return '哈希值';
      default:
        return '文件名';
    }
  };

  return (
    <div className="space-y-6">
      <Card title="文件搜索" className="shadow-sm">
        <div className="space-y-4">
          <div className="flex flex-wrap gap-4">
            <Select
              value={searchType}
              onChange={setSearchType}
              className="w-32"
            >
              <Option value="name">文件名</Option>
              <Option value="path">路径</Option>
              <Option value="hash">哈希值</Option>
            </Select>
            <Input
              placeholder={`请输入要搜索的${getSearchTypeText()}`}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyPress={handleKeyPress}
              className="flex-1 min-w-80"
            />
            <Button
              type="primary"
              icon={<SearchOutlined />}
              onClick={handleSearch}
              loading={loading}
            >
              搜索
            </Button>
          </div>

          {searchType === 'hash' && (
            <div className="text-sm text-gray-600 bg-blue-50 p-3 rounded-lg">
              提示：哈希值搜索支持部分匹配，可以输入 MD5、SHA1 或 SHA256 的一部分
            </div>
          )}
        </div>
      </Card>

      {searchResults.length > 0 && (
        <Card title={`搜索结果 (${searchResults.length} 个文件)`} className="shadow-sm">
          <div className="overflow-hidden rounded-lg border border-gray-200">
            <div className="overflow-x-auto">
              <Table
                columns={columns}
                dataSource={searchResults}
                rowKey={(record) => `${record.meta.id || record.meta.path}`}
                loading={loading}
                pagination={{
                  showSizeChanger: true,
                  showQuickJumper: true,
                  showTotal: (total, range) => `第 ${range[0]}-${range[1]} 条，共 ${total} 条`,
                  pageSizeOptions: ['10', '20', '50', '100'],
                }}
                scroll={{ x: 1600 }}
                size="small"
                className="min-w-full"
              />
            </div>
          </div>
        </Card>
      )}
    </div>
  );
};

export default SearchPage;