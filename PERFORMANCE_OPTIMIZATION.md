# 后端性能优化指南

## 优化概述

本次优化针对 Home-Cloud-Server 的以下性能瓶颈：

1. **数据库查询性能** - N+1 查询、缺少索引、频繁聚合计算
2. **存储统计计算** - 每次请求都重新计算用户存储使用量
3. **文件操作** - 同步处理大文件、缺少流式处理
4. **缓存缺失** - 重复查询数据库获取相同数据

## 优化内容

### 1. 数据库索引优化
- 为频繁查询的字段添加索引
- 优化复合索引策略

### 2. 缓存层 (Redis/Flask-Caching)
- 用户存储使用量缓存
- 文件列表缓存
- 系统设置缓存

### 3. 异步任务队列 (Celery)
- 大文件处理异步化
- 批量操作异步化
- 日志记录异步化

### 4. 数据库连接池
- SQLAlchemy 连接池配置
- 连接回收和超时设置

### 5. 查询优化
- 使用 joinedload 避免 N+1 查询
- 分页查询优化
- 批量操作优化

## 安装依赖

```bash
pip install flask-caching redis celery sqlalchemy-utils
```

## 配置说明

### 环境变量
```bash
# 缓存配置
CACHE_TYPE=redis
CACHE_REDIS_URL=redis://localhost:6379/0

# Celery 配置
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# 数据库连接池
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800
```
