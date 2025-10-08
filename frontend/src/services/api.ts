import axios from 'axios';
import { PaginatedFiles, Statistics, DuplicateFiles, FileWithHash, TreeData } from '../types/api';

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,  // 增加到30秒，因为大数据量查询可能较慢
});

export const fileAPI = {
  // 获取文件列表
  getFiles: async (params: {
    page?: number;
    per_page?: number;
    name?: string;
    path?: string;
    machine?: string;
    min_size?: number;
    max_size?: number;
    hash_value?: string;
  }): Promise<PaginatedFiles> => {
    const response = await api.get('/files', { params });
    return response.data;
  },

  // 搜索文件
  searchFiles: async (query: string, searchType: 'name' | 'path' | 'hash'): Promise<FileWithHash[]> => {
    const response = await api.get('/search', {
      params: { query, search_type: searchType }
    });
    return response.data;
  },

  // 获取统计信息
  getStatistics: async (): Promise<Statistics> => {
    const response = await api.get('/statistics');
    return response.data;
  },

  // 获取重复文件
  getDuplicateFiles: async (params?: {
    page?: number;
    per_page?: number;
    min_size?: number;
    min_count?: number;
    sort_by?: string;
  }): Promise<DuplicateFiles> => {
    const response = await api.get('/duplicates', { params });
    return response.data;
  },

  // 健康检查
  healthCheck: async (): Promise<{ status: string }> => {
    const response = await api.get('/health');
    return response.data;
  },

  // 获取树形结构数据
  getTreeData: async (path: string = ''): Promise<TreeData> => {
    const response = await api.get('/tree', {
      params: { path }
    });
    return response.data;
  },
};

export default api;