import React, { useState, useEffect } from 'react';
import { Layout, Tree, Table, Card, Tag, message, Drawer, Descriptions } from 'antd';
import { FolderOutlined, FileOutlined, FolderOpenOutlined } from '@ant-design/icons';
import type { DataNode } from 'antd/es/tree';
import type { ColumnsType } from 'antd/es/table';
import { fileAPI } from '../services/api';
import { TreeData, TreeFileInfo } from '../types/api';
import EllipsisWithTooltip from './EllipsisWithTooltip';

const { Sider, Content } = Layout;

interface TreeNodeData extends DataNode {
  path: string;
  isLeaf?: boolean;
}

const FileTreePage: React.FC = () => {
  const [treeData, setTreeData] = useState<TreeNodeData[]>([]);
  const [currentPath, setCurrentPath] = useState<string>('/');
  const [files, setFiles] = useState<TreeFileInfo[]>([]);
  const [directories, setDirectories] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedFile, setSelectedFile] = useState<TreeFileInfo | null>(null);
  const [drawerVisible, setDrawerVisible] = useState(false);

  const formatFileSize = (bytes: number): string => {
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

  // 加载树数据
  const loadTreeData = async (path: string = '') => {
    setLoading(true);
    try {
      const data: TreeData = await fileAPI.getTreeData(path);
      setCurrentPath(data.current_path);
      setFiles(data.files);
      setDirectories(data.directories);
    } catch (error) {
      message.error('加载目录数据失败');
      console.error('Error loading tree data:', error);
    } finally {
      setLoading(false);
    }
  };

  // 初始化根节点
  useEffect(() => {
    const initTree = async () => {
      try {
        const data = await fileAPI.getTreeData('');
        const rootNodes: TreeNodeData[] = data.directories.map(machine => ({
          title: machine,
          key: `/${machine}`,
          path: `/${machine}`,
          icon: <FolderOutlined />,
          isLeaf: false,
        }));
        setTreeData(rootNodes);
        setCurrentPath('/');
      } catch (error) {
        message.error('初始化目录树失败');
      }
    };
    initTree();
  }, []);

  // 动态加载子节点
  const onLoadData = async (node: TreeNodeData): Promise<void> => {
    if (node.children) {
      return;
    }

    try {
      const data = await fileAPI.getTreeData(node.path);
      const children: TreeNodeData[] = data.directories.map(dir => ({
        title: dir,
        key: `${node.path}/${dir}`,
        path: `${node.path}/${dir}`,
        icon: <FolderOutlined />,
        isLeaf: false,
      }));

      setTreeData(origin =>
        updateTreeData(origin, node.key as string, children)
      );
    } catch (error) {
      message.error('加载子目录失败');
    }
  };

  // 更新树数据
  const updateTreeData = (
    list: TreeNodeData[],
    key: string,
    children: TreeNodeData[]
  ): TreeNodeData[] => {
    return list.map(node => {
      if (node.key === key) {
        return { ...node, children };
      }
      if (node.children) {
        return {
          ...node,
          children: updateTreeData(node.children as TreeNodeData[], key, children),
        };
      }
      return node;
    });
  };

  // 选择节点时加载文件列表
  const onSelect = async (selectedKeys: React.Key[]) => {
    if (selectedKeys.length > 0) {
      const path = selectedKeys[0] as string;
      await loadTreeData(path);
    }
  };

  // 文件列表列定义
  const fileColumns: ColumnsType<TreeFileInfo> = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: '40%',
      ellipsis: true,
      render: (name, record) => (
        <span
          className="cursor-pointer hover:text-blue-600"
          onClick={() => {
            setSelectedFile(record);
            setDrawerVisible(true);
          }}
        >
          <FileOutlined className="mr-2" />
          <EllipsisWithTooltip text={name}>{name}</EllipsisWithTooltip>
        </span>
      ),
    },
    {
      title: '大小',
      dataIndex: 'size',
      key: 'size',
      width: '20%',
      render: (size) => formatFileSize(size),
    },
    {
      title: '修改时间',
      dataIndex: 'modified',
      key: 'modified',
      width: '40%',
      render: (date) => formatDate(date),
    },
  ];

  // 目录列表列定义
  const dirColumns: ColumnsType<{ name: string }> = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (name) => (
        <span>
          <FolderOutlined className="mr-2 text-blue-500" />
          {name}
        </span>
      ),
    },
  ];

  return (
    <Layout className="h-full">
      <Sider width={300} className="bg-white border-r border-gray-200" theme="light">
        <div className="p-4 border-b border-gray-200">
          <h3 className="text-lg font-semibold m-0">目录树</h3>
        </div>
        <div className="p-2 overflow-auto" style={{ height: 'calc(100% - 64px)' }}>
          <Tree
            showIcon
            loadData={onLoadData}
            treeData={treeData}
            onSelect={onSelect}
            switcherIcon={<FolderOpenOutlined />}
          />
        </div>
      </Sider>

      <Content className="p-4 bg-gray-50">
        <Card
          title={
            <div className="flex items-center justify-between">
              <span>
                当前路径: <Tag color="blue">{currentPath}</Tag>
              </span>
              <span className="text-sm text-gray-500">
                {directories.length} 个文件夹, {files.length} 个文件
              </span>
            </div>
          }
          loading={loading}
        >
          {/* 目录列表 */}
          {directories.length > 0 && (
            <div className="mb-4">
              <Table
                columns={dirColumns}
                dataSource={directories.map(dir => ({ name: dir, key: dir }))}
                pagination={false}
                size="small"
                showHeader={false}
                onRow={(record) => ({
                  onClick: () => {
                    const newPath = `${currentPath}/${record.name}`.replace('//', '/');
                    loadTreeData(newPath);
                  },
                  className: 'cursor-pointer hover:bg-blue-50',
                })}
              />
            </div>
          )}

          {/* 文件列表 */}
          <Table
            columns={fileColumns}
            dataSource={files}
            rowKey={(record) => record.name}
            pagination={{
              showSizeChanger: true,
              showTotal: (total) => `共 ${total} 个文件`,
              pageSizeOptions: ['10', '20', '50', '100'],
            }}
            size="small"
          />
        </Card>
      </Content>

      {/* 文件详情抽屉 */}
      <Drawer
        title="文件详情"
        placement="right"
        width={500}
        onClose={() => setDrawerVisible(false)}
        open={drawerVisible}
      >
        {selectedFile && (
          <Descriptions column={1} bordered>
            <Descriptions.Item label="文件名">
              {selectedFile.name}
            </Descriptions.Item>
            <Descriptions.Item label="大小">
              {formatFileSize(selectedFile.size)}
            </Descriptions.Item>
            <Descriptions.Item label="修改时间">
              {formatDate(selectedFile.modified)}
            </Descriptions.Item>
            {selectedFile.hash && (
              <>
                <Descriptions.Item label="MD5">
                  <code className="text-xs">{selectedFile.hash.md5}</code>
                </Descriptions.Item>
                <Descriptions.Item label="SHA1">
                  <code className="text-xs">{selectedFile.hash.sha1}</code>
                </Descriptions.Item>
                <Descriptions.Item label="SHA256">
                  <code className="text-xs">{selectedFile.hash.sha256}</code>
                </Descriptions.Item>
              </>
            )}
          </Descriptions>
        )}
      </Drawer>
    </Layout>
  );
};

export default FileTreePage;
