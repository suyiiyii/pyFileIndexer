export interface FileHash {
  id?: number;
  size: number;
  md5: string;
  sha1: string;
  sha256: string;
}

export interface FileMeta {
  id?: number;
  hash_id?: number;
  name: string;
  path: string;
  machine: string;
  created: string;
  modified: string;
  scanned: string;
  operation: string;
}

export interface FileWithHash {
  meta: FileMeta;
  hash?: FileHash;
}

export interface PaginatedFiles {
  files: FileWithHash[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface Statistics {
  total_files: number;
  total_size: number;
  machine_stats: Record<string, number>;
  duplicate_files: number;
}

export interface DuplicateFileGroup {
  hash: string;
  files: FileWithHash[];
}

export interface DuplicateFiles {
  duplicates: DuplicateFileGroup[];
  total_groups: number;   // 总重复组数
  total_files: number;    // 本页的总重复文件数
  page: number;
  per_page: number;
  pages: number;          // 总页数
}

export interface SearchFilters {
  name?: string;
  path?: string;
  machine?: string;
  min_size?: number;
  max_size?: number;
  hash_value?: string;
}

export interface TreeFileInfo {
  name: string;
  size: number;
  modified: string;
  hash?: FileHash;
}

export interface TreeData {
  current_path: string;
  directories: string[];
  files: TreeFileInfo[];
}