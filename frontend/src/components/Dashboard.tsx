import React, { useState, useEffect } from 'react';
import { Card, Statistic, Table, Tag, message, Button } from 'antd';
import { FileOutlined, HddOutlined, CopyOutlined, DesktopOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { fileAPI } from '../services/api';
import { Statistics } from '../types/api';

const Dashboard: React.FC = () => {
  const [statistics, setStatistics] = useState<Statistics | null>(null);
  const [loading, setLoading] = useState(false);

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

  useEffect(() => {
    fetchStatistics();
  }, []);

  const handleRefresh = () => {
    fetchStatistics();
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
        <Button icon={<ReloadOutlined />} onClick={handleRefresh} loading={loading}>
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
    </div>
  );
};

export default Dashboard;