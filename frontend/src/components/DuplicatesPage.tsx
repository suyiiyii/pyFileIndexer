import React, { useState, useEffect } from 'react';
import { Card, Table, Tag, Collapse, message, Button, Pagination, InputNumber, Select, Space, Statistic } from 'antd';
import { CopyOutlined, ReloadOutlined, FilterOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { fileAPI } from '../services/api';
import { DuplicateFileGroup, FileWithHash } from '../types/api';
import EllipsisWithTooltip from './EllipsisWithTooltip';

const { Panel } = Collapse;

const DuplicatesPage: React.FC = () => {
  const [duplicates, setDuplicates] = useState<DuplicateFileGroup[]>([]);
  const [loading, setLoading] = useState(false);

  // 分页和过滤器状态
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(20);
  const [totalGroups, setTotalGroups] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [minSize, setMinSize] = useState(1);  // 默认1MB
  const [minCount, setMinCount] = useState(2);  // 默认最少2个重复
  const [sortBy, setSortBy] = useState('count_desc');  // 默认按重复数量降序

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B';
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

  // 获取最常用的文件名
  const getMostCommonFileName = (files: FileWithHash[]): { name: string; count: number } => {
    const nameCount = new Map<string, number>();

    files.forEach(file => {
      const name = file.meta.name;
      nameCount.set(name, (nameCount.get(name) || 0) + 1);
    });

    let mostCommonName = '';
    let maxCount = 0;

    nameCount.forEach((count, name) => {
      if (count > maxCount) {
        maxCount = count;
        mostCommonName = name;
      }
    });

    return { name: mostCommonName, count: maxCount };
  };

  const duplicateFileColumns: ColumnsType<FileWithHash> = [
    {
      title: '文件名',
      dataIndex: ['meta', 'name'],
      key: 'name',
      width: 200,
      ellipsis: true,
      render: (name) => <EllipsisWithTooltip text={name} showCopyIcon />,
    },
    {
      title: '路径',
      dataIndex: ['meta', 'path'],
      key: 'path',
      width: 350,
      ellipsis: true,
      render: (path) => <EllipsisWithTooltip text={path} showCopyIcon />,
    },
    {
      title: '大小',
      key: 'size',
      width: 100,
      render: (_, record) => formatFileSize(record.hash?.size || 0),
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
  ];

  const fetchDuplicates = async () => {
    setLoading(true);
    try {
      const response = await fileAPI.getDuplicateFiles({
        page,
        per_page: perPage,
        min_size: minSize * 1048576,  // 转换为字节
        min_count: minCount,
        sort_by: sortBy,
      });
      setDuplicates(response.duplicates);
      setTotalGroups(response.total_groups);
      setTotalPages(response.pages);
    } catch (error) {
      message.error('获取重复文件失败');
      console.error('Error fetching duplicates:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDuplicates();
  }, [page, perPage, minSize, minCount, sortBy]);

  const handleRefresh = () => {
    fetchDuplicates();
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-semibold text-gray-800 m-0">重复文件管理</h2>
        <Button icon={<ReloadOutlined />} onClick={handleRefresh} loading={loading}>
          刷新数据
        </Button>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card loading={loading} className="hover:shadow-md transition-shadow">
          <Statistic
            title="重复文件组总数"
            value={totalGroups}
            prefix={<CopyOutlined />}
            formatter={(value) => value?.toLocaleString()}
          />
        </Card>
        <Card loading={loading} className="hover:shadow-md transition-shadow">
          <Statistic
            title="当前页组数"
            value={duplicates.length}
            formatter={(value) => value?.toLocaleString()}
          />
        </Card>
        <Card loading={loading} className="hover:shadow-md transition-shadow">
          <Statistic
            title="当前页文件数"
            value={duplicates.reduce((sum, group) => sum + group.files.length, 0)}
            formatter={(value) => value?.toLocaleString()}
          />
        </Card>
      </div>

      {/* 过滤器 */}
      <Card title={<span><FilterOutlined className="mr-2" />过滤器与排序</span>} className="hover:shadow-md transition-shadow">
        <Space size="large" wrap>
          <div>
            <label className="block text-sm text-gray-600 mb-1">最小文件大小 (MB):</label>
            <InputNumber
              min={0}
              value={minSize}
              onChange={(value) => {
                setMinSize(value || 1);
                setPage(1); // 重置到第一页
              }}
              style={{ width: 150 }}
            />
          </div>
          <div>
            <label className="block text-sm text-gray-600 mb-1">最小重复数量:</label>
            <Select
              value={minCount}
              onChange={(value) => {
                setMinCount(value);
                setPage(1); // 重置到第一页
              }}
              style={{ width: 150 }}
              options={[
                { value: 2, label: '2个及以上' },
                { value: 3, label: '3个及以上' },
                { value: 5, label: '5个及以上' },
                { value: 10, label: '10个及以上' },
              ]}
            />
          </div>
          <div>
            <label className="block text-sm text-gray-600 mb-1">排序方式:</label>
            <Select
              value={sortBy}
              onChange={(value) => {
                setSortBy(value);
                setPage(1); // 重置到第一页
              }}
              style={{ width: 180 }}
              options={[
                { value: 'count_desc', label: '按重复数量 ↓ (最多)' },
                { value: 'count_asc', label: '按重复数量 ↑ (最少)' },
                { value: 'size_desc', label: '按文件大小 ↓ (最大)' },
                { value: 'size_asc', label: '按文件大小 ↑ (最小)' },
              ]}
            />
          </div>
          <div>
            <label className="block text-sm text-gray-600 mb-1">每页显示:</label>
            <Select
              value={perPage}
              onChange={(value) => {
                setPerPage(value);
                setPage(1); // 重置到第一页
              }}
              style={{ width: 150 }}
              options={[
                { value: 10, label: '10 组/页' },
                { value: 20, label: '20 组/页' },
                { value: 50, label: '50 组/页' },
                { value: 100, label: '100 组/页' },
              ]}
            />
          </div>
        </Space>
      </Card>

      {/* 重复文件列表 */}
      {duplicates.length > 0 ? (
        <Card
          title={`重复文件详情 (第 ${page} / ${totalPages} 页)`}
          loading={loading}
          className="hover:shadow-md transition-shadow"
        >
          <Collapse className="bg-gray-50">
            {duplicates.map((group, index) => {
              const mostCommon = getMostCommonFileName(group.files);
              return (
                <Panel
                  header={
                    <div className="flex items-center flex-wrap gap-2">
                      <Tag color="orange">{group.files.length} 个文件</Tag>
                      {mostCommon.name && (
                        <span className="text-sm">
                          常用名: <Tag color="green">{mostCommon.name}</Tag>
                          {mostCommon.count > 1 && <span className="text-xs text-gray-500">({mostCommon.count}个)</span>}
                        </span>
                      )}
                      <span className="text-sm">
                        MD5: <code className="text-xs bg-gray-100 px-1 rounded">{group.hash}</code>
                      </span>
                      <span className="text-gray-600 text-sm">
                        大小: {formatFileSize(group.files[0]?.hash?.size || 0)}
                      </span>
                    </div>
                  }
                  key={index}
                >
                <div className="overflow-x-auto">
                  <Table
                    columns={duplicateFileColumns}
                    dataSource={group.files}
                    rowKey={(record) => `${record.meta.id || record.meta.path}`}
                    size="small"
                    pagination={false}
                    className="min-w-full"
                  />
                </div>
              </Panel>
              );
            })}
          </Collapse>
          <div className="mt-4 flex justify-center">
            <Pagination
              current={page}
              total={totalGroups}
              pageSize={perPage}
              onChange={(newPage) => setPage(newPage)}
              showTotal={(total) => `共 ${total} 组重复文件`}
              showSizeChanger={false}
            />
          </div>
        </Card>
      ) : (
        <Card className="hover:shadow-md transition-shadow">
          <div className="text-center py-10 text-gray-400">
            <CopyOutlined style={{ fontSize: 48, marginBottom: 16 }} />
            <div>未找到符合条件的重复文件</div>
          </div>
        </Card>
      )}
    </div>
  );
};

export default DuplicatesPage;
