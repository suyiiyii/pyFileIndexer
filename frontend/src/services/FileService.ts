import { fileAPI } from './api';
import { TreeData } from '../types/api';

interface CacheItem {
  data: TreeData;
  timestamp: number;
  isLoading: boolean;
  error: Error | null;
}

interface FileServiceCallbacks {
  onDataUpdate?: (path: string, data: TreeData) => void;
  onLoadingChange?: (path: string, isLoading: boolean) => void;
  onError?: (path: string, error: Error) => void;
}

class FileService {
  private cache = new Map<string, CacheItem>();
  private callbacks = new Set<FileServiceCallbacks>();
  private cacheTimeout = 5 * 60 * 1000; // 5分钟缓存过期
  private pendingRequests = new Map<string, Promise<TreeData>>();
  private prefetchQueue = new Set<string>();
  private lastAccessedPaths = new Map<string, number>(); // 跟踪最近访问的路径

  /**
   * 注册回调函数
   */
  public subscribe(callbacks: FileServiceCallbacks): () => void {
    this.callbacks.add(callbacks);
    return () => this.callbacks.delete(callbacks);
  }

  /**
   * 通知所有订阅者
   */
  private notify(path: string, type: keyof FileServiceCallbacks, data?: any) {
    this.callbacks.forEach(callback => {
      const fn = callback[type];
      if (fn) {
        fn(path, data);
      }
    });
  }

  /**
   * 检查缓存是否过期
   */
  private isCacheExpired(timestamp: number): boolean {
    return Date.now() - timestamp > this.cacheTimeout;
  }

  /**
   * 清理过期缓存
   */
  private cleanExpiredCache() {
    for (const [path, item] of this.cache.entries()) {
      if (this.isCacheExpired(item.timestamp) && !item.isLoading) {
        this.cache.delete(path);
      }
    }
  }

  /**
   * 获取路径的树形数据
   */
  public async getTreeData(path: string = ''): Promise<TreeData> {
    this.cleanExpiredCache();

    const cacheKey = path || '/';
    const cached = this.cache.get(cacheKey);

    // 记录访问时间和路径
    this.lastAccessedPaths.set(cacheKey, Date.now());

    // 如果有有效的缓存且正在加载，返回现有数据
    if (cached && !this.isCacheExpired(cached.timestamp)) {
      console.log(`[FileService] 使用缓存数据: ${cacheKey}`);
      return cached.data;
    }

    // 如果正在请求中，返回现有的Promise
    if (cached?.isLoading) {
      console.log(`[FileService] 等待正在进行的请求: ${cacheKey}`);
      const pendingRequest = this.pendingRequests.get(cacheKey);
      if (pendingRequest) {
        return pendingRequest;
      }
    }

    // 创建新的请求
    const requestPromise = this.fetchTreeData(cacheKey);
    this.pendingRequests.set(cacheKey, requestPromise);

    try {
      const data = await requestPromise;

      // 智能预加载：预加载可能的子目录
      this.smartPrefetch(data, cacheKey);

      return data;
    } finally {
      this.pendingRequests.delete(cacheKey);
    }
  }

  /**
   * 实际发起API请求
   */
  private async fetchTreeData(path: string): Promise<TreeData> {
    console.log(`[FileService] 发起API请求: ${path}`);

    // 更新缓存状态为加载中
    this.cache.set(path, {
      data: this.cache.get(path)?.data || { current_path: path, directories: [], files: [] },
      timestamp: Date.now(),
      isLoading: true,
      error: null,
    });

    this.notify(path, 'onLoadingChange', true);

    try {
      const data = await fileAPI.getTreeData(path === '/' ? '' : path);

      // 更新缓存
      this.cache.set(path, {
        data,
        timestamp: Date.now(),
        isLoading: false,
        error: null,
      });

      this.notify(path, 'onDataUpdate', data);
      this.notify(path, 'onLoadingChange', false);

      return data;
    } catch (error) {
      const err = error as Error;

      // 更新缓存状态
      this.cache.set(path, {
        data: this.cache.get(path)?.data || { current_path: path, directories: [], files: [] },
        timestamp: Date.now(),
        isLoading: false,
        error: err,
      });

      this.notify(path, 'onError', err);
      this.notify(path, 'onLoadingChange', false);

      throw err;
    }
  }

  /**
   * 预加载路径数据
   */
  public async preloadPath(path: string): Promise<void> {
    try {
      await this.getTreeData(path);
    } catch (error) {
      console.warn(`[FileService] 预加载失败: ${path}`, error);
    }
  }

  /**
   * 强制刷新指定路径的数据
   */
  public async refreshPath(path: string = ''): Promise<TreeData> {
    console.log(`[FileService] 强制刷新: ${path}`);
    const cacheKey = path || '/';
    this.cache.delete(cacheKey);
    return this.getTreeData(path);
  }

  /**
   * 清空所有缓存
   */
  public clearCache(): void {
    this.cache.clear();
    console.log('[FileService] 缓存已清空');
  }

  /**
   * 获取缓存状态
   */
  public getCacheInfo(): {
    size: number;
    paths: string[];
    loadingPaths: string[];
  } {
    const paths = Array.from(this.cache.keys());
    const loadingPaths = paths.filter(path => this.cache.get(path)?.isLoading);

    return {
      size: this.cache.size,
      paths,
      loadingPaths,
    };
  }

  /**
   * 检查路径是否正在加载
   */
  public isLoading(path: string = ''): boolean {
    const cacheKey = path || '/';
    return this.cache.get(cacheKey)?.isLoading || false;
  }

  /**
   * 获取缓存的错误信息
   */
  public getError(path: string = ''): Error | null {
    const cacheKey = path || '/';
    return this.cache.get(cacheKey)?.error || null;
  }

  /**
   * 批量预加载多个路径
   */
  public async preloadPaths(paths: string[]): Promise<void> {
    const promises = paths.map(path => this.preloadPath(path));
    await Promise.allSettled(promises);
  }

  /**
   * 智能预加载：根据访问模式预加载可能的路径
   */
  private smartPrefetch(data: TreeData, currentPath: string): void {
    // 预加载策略：预加载前几个子目录
    if (data.directories && data.directories.length > 0) {
      const prefetchCount = Math.min(2, data.directories.length); // 最多预加载2个子目录
      const dirsToPrefetch = data.directories.slice(0, prefetchCount);

      setTimeout(() => {
        dirsToPrefetch.forEach(dir => {
          const childPath = `${currentPath}/${dir}`.replace('//', '/');
          if (!this.prefetchQueue.has(childPath) && !this.cache.has(childPath)) {
            this.prefetchQueue.add(childPath);
            this.preloadPath(childPath).finally(() => {
              this.prefetchQueue.delete(childPath);
            });
          }
        });
      }, 100); // 延迟100ms，避免影响当前响应
    }
  }

  /**
   * 获取最近访问的路径（用于分析用户行为）
   */
  public getRecentPaths(limit: number = 5): string[] {
    const paths = Array.from(this.lastAccessedPaths.entries())
      .sort(([, a], [, b]) => b - a) // 按时间倒序
      .slice(0, limit)
      .map(([path]) => path);

    return paths;
  }

  /**
   * 清理旧的访问记录（只保留最近的记录）
   */
  private cleanOldAccessRecords(): void {
    const maxRecords = 50;
    if (this.lastAccessedPaths.size > maxRecords) {
      const entries = Array.from(this.lastAccessedPaths.entries())
        .sort(([, a], [, b]) => b - a)
        .slice(0, maxRecords);

      this.lastAccessedPaths.clear();
      entries.forEach(([path, time]) => {
        this.lastAccessedPaths.set(path, time);
      });
    }
  }

  /**
   * 获取服务统计信息
   */
  public getServiceStats(): {
    cacheSize: number;
    pendingRequests: number;
    prefetchQueueSize: number;
    recentPaths: string[];
    totalRequests: number;
  } {
    this.cleanOldAccessRecords();

    return {
      cacheSize: this.cache.size,
      pendingRequests: this.pendingRequests.size,
      prefetchQueueSize: this.prefetchQueue.size,
      recentPaths: this.getRecentPaths(3),
      totalRequests: this.getCacheInfo().loadingPaths.length
    };
  }
}

// 创建单例实例
const fileService = new FileService();

export default fileService;