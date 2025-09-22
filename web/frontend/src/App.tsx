import React from 'react';
import { Layout, Menu, ConfigProvider } from 'antd';
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import { DashboardOutlined, FileSearchOutlined, UnorderedListOutlined } from '@ant-design/icons';
import zhCN from 'antd/locale/zh_CN';
import Dashboard from './components/Dashboard';
import FileList from './components/FileList';
import SearchPage from './components/SearchPage';
import './App.css';

const { Header, Content, Sider } = Layout;

const AppContent: React.FC = () => {
  const location = useLocation();

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
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={200} theme="light">
        <div style={{ height: 32, margin: 16, fontSize: 18, fontWeight: 'bold', textAlign: 'center' }}>
          pyFileIndexer
        </div>
        <Menu
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
        />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', padding: '0 24px', borderBottom: '1px solid #f0f0f0' }}>
          <h1 style={{ margin: 0, fontSize: 20 }}>文件索引系统</h1>
        </Header>
        <Content style={{ margin: '24px', background: '#fff', minHeight: 280 }}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/files" element={<FileList />} />
            <Route path="/search" element={<SearchPage />} />
          </Routes>
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
