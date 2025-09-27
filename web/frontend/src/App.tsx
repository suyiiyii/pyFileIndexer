import React, { useState, useEffect } from 'react';
import { Layout, Menu, ConfigProvider } from 'antd';
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import { DashboardOutlined, FileSearchOutlined, UnorderedListOutlined, MenuOutlined } from '@ant-design/icons';
import zhCN from 'antd/locale/zh_CN';
import Dashboard from './components/Dashboard';
import FileList from './components/FileList';
import SearchPage from './components/SearchPage';

const { Header, Content, Sider } = Layout;

const AppContent: React.FC = () => {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
      if (mobile) {
        setCollapsed(true);
      }
    };

    window.addEventListener('resize', handleResize);
    handleResize(); // 初始检查

    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const menuItems = [
    {
      key: '/',
      icon: <DashboardOutlined />,
      label: <Link to="/">统计面板</Link>,
    },
    {
      key: '/files',
      icon: <UnorderedListOutlined />,
      label: <Link to="/files">文件列表</Link>,
    },
    {
      key: '/search',
      icon: <FileSearchOutlined />,
      label: <Link to="/search">文件搜索</Link>,
    },
  ];

  return (
    <Layout className="min-h-screen bg-gray-50">
      <Sider 
        width={200} 
        theme="light" 
        className="bg-white border-r border-gray-200 shadow-sm" 
        collapsed={collapsed}
        collapsible={isMobile}
        trigger={null}
        breakpoint="lg"
        onBreakpoint={(broken) => {
          if (broken) {
            setCollapsed(true);
          }
        }}
      >
        {!collapsed && (
          <div className="h-12 mx-4 my-4 text-lg font-bold text-center text-gray-800 flex items-center justify-center bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg">
            pyFileIndexer
          </div>
        )}
        {collapsed && (
          <div className="h-12 mx-2 my-4 text-sm font-bold text-center text-gray-800 flex items-center justify-center bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg">
            pFI
          </div>
        )}
        <Menu
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          className="border-none"
          inlineCollapsed={collapsed}
        />
      </Sider>
      <Layout className="bg-gray-50">
        <Header className="bg-white px-6 border-b border-gray-200 flex items-center justify-between shadow-sm">
          <div className="flex items-center gap-4">
            {isMobile && (
              <MenuOutlined 
                className="text-lg cursor-pointer hover:text-blue-600 transition-colors" 
                onClick={() => setCollapsed(!collapsed)}
              />
            )}
            <h1 className="text-xl font-semibold text-gray-800 m-0">文件索引系统</h1>
          </div>
        </Header>
        <Content className="m-6 overflow-auto">
          <div className="bg-white rounded-lg shadow-sm p-6 min-h-[calc(100vh-8rem)] animate-fade-in">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/files" element={<FileList />} />
              <Route path="/search" element={<SearchPage />} />
            </Routes>
          </div>
        </Content>
      </Layout>
    </Layout>
  );
};

const App: React.FC = () => {
  return (
    <ConfigProvider locale={zhCN}>
      <Router>
        <AppContent />
      </Router>
    </ConfigProvider>
  );
};

export default App;
