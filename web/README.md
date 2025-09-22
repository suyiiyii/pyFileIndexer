# pyFileIndexer Web UI

基于 FastAPI + React 18 + Ant Design 的文件索引系统 Web 界面。

## 功能特性

### 后端 API (FastAPI)
- 文件列表查询，支持分页和多条件过滤
- 文件搜索（按文件名、路径、哈希值）
- 统计信息展示
- 重复文件检测
- 自动生成 API 文档

### 前端界面 (React + Ant Design)
- 📊 **统计面板**: 文件总数、总大小、按机器统计、重复文件概览
- 📋 **文件列表**: 分页展示，支持多条件搜索过滤
- 🔍 **文件搜索**: 支持文件名、路径、哈希值搜索，搜索结果高亮显示
- 🔄 **重复文件**: 按哈希值分组展示重复文件

## 快速开始

### 1. 安装依赖

```bash
# 安装 Python 依赖
cd ../../
uv sync

# 安装前端依赖
cd web/frontend
npm install
```

### 2. 启动后端服务

```bash
# 从项目根目录启动
cd ../../
uv run python web/backend/app.py

# 或者使用 uvicorn 直接启动
cd web/backend
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

后端服务将在 http://localhost:8000 启动，API 文档可在 http://localhost:8000/docs 查看。

### 3. 启动前端开发服务器

```bash
cd web/frontend
npm run dev
```

前端服务将在 http://localhost:3000 启动。

## 项目结构

```
web/
├── backend/                 # FastAPI 后端
│   ├── app.py              # FastAPI 应用主文件
│   ├── api/                # API 路由
│   └── models/             # Pydantic 响应模型
│       └── responses.py
└── frontend/               # React 前端
    ├── src/
    │   ├── components/     # React 组件
    │   │   ├── Dashboard.tsx
    │   │   ├── FileList.tsx
    │   │   └── SearchPage.tsx
    │   ├── services/       # API 调用服务
    │   │   └── api.ts
    │   ├── types/          # TypeScript 类型定义
    │   │   └── api.ts
    │   └── App.tsx
    ├── package.json
    └── vite.config.ts
```

## API 端点

### 文件操作
- `GET /api/files` - 获取文件列表（支持分页和过滤）
- `GET /api/search` - 搜索文件
- `GET /api/statistics` - 获取统计信息
- `GET /api/duplicates` - 获取重复文件

### 查询参数
#### 文件列表过滤
- `page`: 页码（默认: 1）
- `per_page`: 每页数量（默认: 20，最大: 100）
- `name`: 文件名过滤
- `path`: 路径过滤
- `machine`: 机器名过滤
- `min_size`: 最小文件大小
- `max_size`: 最大文件大小
- `hash_value`: 哈希值过滤

#### 文件搜索
- `query`: 搜索关键词
- `search_type`: 搜索类型（name/path/hash）

## 开发说明

### 后端开发
- 使用 FastAPI 框架，自动生成 OpenAPI 文档
- 集成现有的 SQLAlchemy 数据模型
- 支持 CORS，允许前端跨域访问
- 统一的错误处理和响应格式

### 前端开发
- 使用 React 18 + TypeScript
- Ant Design 提供 UI 组件
- Axios 处理 API 调用
- React Router 处理页面路由
- Vite 作为构建工具，支持热重载

### 测试
```bash
# 运行后端测试
cd ../../
uv run pytest tests/test_web_api.py -v

# 运行所有测试
uv run pytest
```

## 部署

### 生产环境构建
```bash
# 构建前端
cd web/frontend
npm run build

# 生产环境运行后端
cd ../backend
uvicorn app:app --host 0.0.0.0 --port 8000
```

### Docker 部署
可以扩展现有的 Dockerfile 来支持 Web 服务。

## 特性说明

### 响应式设计
- 支持桌面和移动设备
- 表格自适应屏幕宽度
- 分页和搜索功能在小屏幕上优化

### 性能优化
- 前端代理 API 请求，避免跨域问题
- 分页加载，避免一次性加载大量数据
- 搜索结果高亮显示
- 文件大小人性化显示

### 用户体验
- 中文界面，本地化时间显示
- 操作反馈（loading、成功/错误提示）
- 搜索历史和快捷操作
- 键盘快捷键支持（Enter 搜索）