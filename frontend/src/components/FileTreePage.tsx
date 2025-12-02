import React, { useState, useEffect, useRef } from 'react';
import { Layout, Tree, Table, Card, Tag, message, Drawer, Descriptions, Button, Switch } from 'antd';
import { FolderOutlined, FileOutlined, FolderOpenOutlined, ReloadOutlined, SettingOutlined } from '@ant-design/icons';
import type { DataNode } from 'antd/es/tree';
import type { ColumnsType } from 'antd/es/table';
import fileService from '../services/FileService';
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
  const [expandedKeys, setExpandedKeys] = useState<React.Key[]>([]);
  const [selectedKeys, setSelectedKeys] = useState<React.Key[]>([]);
  const [debugMode, setDebugMode] = useState(false);
  const [debugDrawerVisible, setDebugDrawerVisible] = useState(false);
  const [serviceStats, setServiceStats] = useState<any>(null);

  // 用于管理服务订阅
  const unsubscribeRef = useRef<(() => void) | null>(null);
  const currentLoadPathRef = useRef<string | null>(null);
  const statsIntervalRef = useRef<number | null>(null);

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

  // 获取路径的所有父节点路径
  const getPathSegments = (path: string): string[] => {
    if (!path || path === '/') return [];

    const segments: string[] = [];
    const parts = path.split('/').filter(p => p); // 移除空字符串

    for (let i = 0; i < parts.length; i++) {
      const segment = '/' + parts.slice(0, i + 1).join('/');
      segments.push(segment);
    }

    return segments;
  };

  // 加载树数据并同步树的展开状态
  const loadTreeData = async (path: string = '') => {
    const normalizedPath = path || '/';
    currentLoadPathRef.current = normalizedPath;

    try {
      const data: TreeData = await fileService.getTreeData(path);

      // 如果请求的路径已经不是当前关注的路径，则忽略结果
      if (currentLoadPathRef.current !== normalizedPath) {
        return;
      }

      setCurrentPath(data.current_path);
      setFiles(data.files);
      setDirectories(data.directories);

      // 同步树的展开和选中状态
      if (path && path !== '/') {
        const pathSegments = getPathSegments(path);
        setExpandedKeys(pathSegments);
        setSelectedKeys([path]);
      } else {
        setSelectedKeys([]);
      }
    } catch (error) {
      // 只处理当前路径的错误
      if (currentLoadPathRef.current === normalizedPath) {
        message.error('加载目录数据失败');
        console.error('Error loading tree data:', error);
      }
    }
  };

  // 初始化根节点和服务订阅
  useEffect(() => {
    const initTree = async () => {
      try {
        const data = await fileService.getTreeData('');
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

    // 订阅 FileService 的事件
    unsubscribeRef.current = fileService.subscribe({
      onDataUpdate: (path, data) => {
        if (debugMode) {
          console.log(`[FileTreePage] 收到数据更新: ${path}`);
        }
        // 如果更新的是当前路径，更新UI
        if (path === currentPath || path === '/' || path === currentPath + '/') {
          setCurrentPath(data.current_path);
          setFiles(data.files);
          setDirectories(data.directories);
        }
      },
      onLoadingChange: (path, isLoading) => {
        // 如果是当前路径正在加载，更新加载状态
        if (path === currentPath || path === '/' || path === currentPath + '/') {
          setLoading(isLoading);
        }
      },
      onError: (path, error) => {
        // 如果是当前路径出错，显示错误信息
        if (path === currentPath || path === '/' || path === currentPath + '/') {
          message.error(`加载目录数据失败: ${error.message}`);
        }
      },
    });

    initTree();

    // 清理函数
    return () => {
      if (unsubscribeRef.current) {
        unsubscribeRef.current();
      }
      if (statsIntervalRef.current) {
        clearInterval(statsIntervalRef.current);
      }
    };
  }, [currentPath, debugMode]);

  // 调试模式：定期更新服务统计信息
  useEffect(() => {
    if (debugMode) {
      const updateStats = () => {
        setServiceStats(fileService.getServiceStats());
      };

      updateStats(); // 立即更新一次
      statsIntervalRef.current = setInterval(updateStats, 1000); // 每秒更新

      return () => {
        if (statsIntervalRef.current) {
          clearInterval(statsIntervalRef.current);
        }
      };
    } else {
      setServiceStats(null);
    }
  }, [debugMode]);

  // 动态加载子节点
  const onLoadData = async (node: TreeNodeData): Promise<void> => {
    if (node.children) {
      return;
    }

    try {
      const data = await fileService.getTreeData(node.path);
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

      // 预加载子目录数据
      if (directories.length > 0 && directories.length <= 10) {
        const preloadPaths = directories.slice(0, 3).map(dir => `${path}/${dir}`.replace('//', '/'));
        fileService.preloadPaths(preloadPaths);
      }
    }
  };

  // 刷新当前路径
  const handleRefresh = async () => {
    try {
      await fileService.refreshPath(currentPath);
    } catch (error) {
      message.error('刷新失败');
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
            expandedKeys={expandedKeys}
            selectedKeys={selectedKeys}
            onExpand={(keys) => setExpandedKeys(keys)}
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
              <div className="flex items-center gap-4">
                <span className="text-sm text-gray-500">
                  {directories.length} 个文件夹, {files.length} 个文件
                </span>
                <div className="flex items-center gap-2">
                  {debugMode && (
                    <span className="text-xs text-green-600 bg-green-50 px-2 py-1 rounded">
                      调试模式
                    </span>
                  )}
                  <Switch
                    size="small"
                    checked={debugMode}
                    onChange={setDebugMode}
                    title="切换调试模式"
                  />
                  <Button
                    type="text"
                    size="small"
                    icon={<SettingOutlined />}
                    onClick={() => setDebugDrawerVisible(true)}
                    disabled={!debugMode}
                    title="调试面板"
                  />
                  <Button
                    type="text"
                    size="small"
                    icon={<ReloadOutlined />}
                    onClick={handleRefresh}
                    loading={loading}
                    title="刷新当前目录"
                  />
                </div>
              </div>
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

      {/* 调试面板 */}
      <Drawer
        title="FileService 调试面板"
        placement="right"
        width={400}
        onClose={() => setDebugDrawerVisible(false)}
        open={debugDrawerVisible}
      >
        {serviceStats && (
          <div className="space-y-4">
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="缓存大小">
                <Tag color="blue">{serviceStats.cacheSize}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="等待中请求">
                <Tag color={serviceStats.pendingRequests > 0 ? 'orange' : 'green'}>
                  {serviceStats.pendingRequests}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="预加载队列">
                <Tag color="purple">{serviceStats.prefetchQueueSize}</Tag>
              </Descriptions.Item>
            </Descriptions>

            <div>
              <h4 className="text-sm font-semibold mb-2">最近访问路径</h4>
              <div className="space-y-1">
                {serviceStats.recentPaths.map((path: string, index: number) => (
                  <div key={index} className="text-xs text-gray-600 bg-gray-50 p-1 rounded">
                    {path || '/'}
                  </div>
                ))}
                {serviceStats.recentPaths.length === 0 && (
                  <div className="text-xs text-gray-400">暂无访问记录</div>
                )}
              </div>
            </div>

            <div className="space-y-2">
              <Button
                size="small"
                block
                onClick={() => fileService.clearCache()}
              >
                清空缓存
              </Button>
              <Button
                size="small"
                block
                onClick={() => fileService.refreshPath(currentPath)}
              >
                强制刷新当前路径
              </Button>
            </div>

            <div className="text-xs text-gray-500 space-y-1">
              <div>• 缓存超时: 5分钟</div>
              <div>• 自动预加载: 前2个子目录</div>
              <div>• 请求去重: ✅ 启用</div>
            </div>
          </div>
        )}
      </Drawer>
    </Layout>
  );
};

export default FileTreePage;
