import React, { useState, useEffect } from 'react';
import { Card, Statistic, Table, Tag, Collapse, message, Button } from 'antd';
import { FileOutlined, HddOutlined, CopyOutlined, DesktopOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { fileAPI } from '../services/api';
import { Statistics, DuplicateFileGroup, FileWithHash } from '../types/api';

const { Panel } = Collapse;

const Dashboard: React.FC = () => {
  const [statistics, setStatistics] = useState<Statistics | null>(null);
  const [duplicates, setDuplicates] = useState<DuplicateFileGroup[]>([]);
  const [loading, setLoading] = useState(false);
  const [duplicatesLoading, setDuplicatesLoading] = useState(false);

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

  const duplicateFileColumns: ColumnsType<FileWithHash> = [
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
      width: 350,
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

  const machineStatsColumns: ColumnsType<{ machine: string; count: number }> = [
    {
      title: '机器名',
      dataIndex: 'machine',
      key: 'machine',
      render: (machine) => <Tag color="blue" icon={<DesktopOutlined />}>{machine}</Tag>,
    },
    {
      title: '文件数量',
      dataIndex: 'count',
      key: 'count',
      render: (count) => count.toLocaleString(),
    },
  ];

  const fetchStatistics = async () => {
    setLoading(true);
    try {
      const stats = await fileAPI.getStatistics();
      setStatistics(stats);
    } catch (error) {
      message.error('获取统计信息失败');
      console.error('Error fetching statistics:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchDuplicates = async () => {
    setDuplicatesLoading(true);
    try {
      const response = await fileAPI.getDuplicateFiles();
      setDuplicates(response.duplicates);
    } catch (error) {
      message.error('获取重复文件失败');
      console.error('Error fetching duplicates:', error);
    } finally {
      setDuplicatesLoading(false);
    }
  };

  useEffect(() => {
    fetchStatistics();
    fetchDuplicates();
  }, []);

  const handleRefresh = () => {
    fetchStatistics();
    fetchDuplicates();
  };

  const machineStatsData = statistics
    ? Object.entries(statistics.machine_stats).map(([machine, count]) => ({
        machine,
        count,
      }))
    : [];

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-semibold text-gray-800 m-0">系统统计</h2>
        <Button icon={<ReloadOutlined />} onClick={handleRefresh} loading={loading || duplicatesLoading}>
          刷新数据
        </Button>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card loading={loading} className="hover:shadow-md transition-shadow">
          <Statistic
            title="总文件数"
            value={statistics?.total_files || 0}
            prefix={<FileOutlined />}
            formatter={(value) => value?.toLocaleString()}
          />
        </Card>
        <Card loading={loading} className="hover:shadow-md transition-shadow">
          <Statistic
            title="总大小"
            value={statistics?.total_size || 0}
            prefix={<HddOutlined />}
            formatter={(value) => formatFileSize(Number(value))}
          />
        </Card>
        <Card loading={loading} className="hover:shadow-md transition-shadow">
          <Statistic
            title="重复文件组"
            value={statistics?.duplicate_files || 0}
            prefix={<CopyOutlined />}
            formatter={(value) => value?.toLocaleString()}
          />
        </Card>
        <Card loading={loading} className="hover:shadow-md transition-shadow">
          <Statistic
            title="机器数量"
            value={Object.keys(statistics?.machine_stats || {}).length}
            prefix={<DesktopOutlined />}
          />
        </Card>
      </div>

      {/* 按机器统计 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="按机器统计" loading={loading} className="hover:shadow-md transition-shadow">
          <Table
            columns={machineStatsColumns}
            dataSource={machineStatsData}
            rowKey="machine"
            size="small"
            pagination={false}
            className="overflow-auto"
          />
        </Card>
        <Card title="重复文件概览" loading={duplicatesLoading} className="hover:shadow-md transition-shadow">
          <div className="text-center py-5">
            <div className="text-2xl font-bold text-blue-600">
              {duplicates.length}
            </div>
            <div className="text-gray-600">个重复文件组</div>
            <div className="mt-2 text-xs text-gray-400">
              总计 {duplicates.reduce((sum, group) => sum + group.files.length, 0)} 个重复文件
            </div>
          </div>
        </Card>
      </div>

      {/* 重复文件详情 */}
      {duplicates.length > 0 && (
        <Card title="重复文件详情" loading={duplicatesLoading} className="hover:shadow-md transition-shadow">
          <Collapse className="bg-gray-50">
            {duplicates.map((group, index) => (
              <Panel
                header={
                  <div className="flex items-center space-x-2">
                    <Tag color="orange">{group.files.length} 个文件</Tag>
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
            ))}
          </Collapse>
        </Card>
      )}
    </div>
  );
};

export default Dashboard;