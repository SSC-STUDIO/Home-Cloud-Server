# IDOR 水平越权漏洞修复验证报告

## 漏洞描述
**漏洞类型**: API 水平越权 (IDOR - Insecure Direct Object Reference)  
**风险等级**: 高危  
**影响范围**: 文件下载、文件夹查看、文件分享、文件操作

## 漏洞详情
- **位置**: `app/routes/files.py`, `app/routes/api.py`
- **问题**: 多个 API 和 Web 端点在操作文件/文件夹时未验证当前用户是否有权限访问目标资源
- **影响**: 攻击者可以通过构造请求访问、修改、删除其他用户的文件和文件夹

## 修复内容

### 1. 新增权限验证装饰器和辅助函数 (`files.py`)

```python
# 权限验证装饰器
- require_file_owner(f)          # 验证文件所有权
- require_folder_owner(f)        # 验证文件夹所有权

# 辅助函数
- verify_file_ownership()        # 验证文件归属
- verify_folder_ownership()      # 验证文件夹归属
- get_user_file_or_404()         # 获取用户文件或404
- get_user_folder_or_404()       # 获取用户文件夹或404
- get_user_files_in_folder()     # 安全获取文件夹内文件
- get_user_subfolders()          # 安全获取子文件夹
```

### 2. 修复的具体函数

#### `files.py` 中的修复：

| 函数 | 修复内容 |
|------|----------|
| `get_files_page_context()` | 添加父文件夹所有权验证 |
| `delete_folder()` | 递归删除子文件夹时添加 `user_id` 验证 |
| `trash()` (回收站视图) | 递归获取子文件夹树时添加 `user_id` 验证 |
| `restore_file()` | 恢复父文件夹时添加 `user_id` 验证 |
| `restore_folder()` | 递归恢复子文件夹和文件时添加 `user_id` 验证 |
| `batch_restore()` | 批量恢复时所有查询添加 `user_id` 验证 |
| `batch_move()` | `is_descendant()` 函数添加 `user_id` 验证 |

#### `api.py` 中新增的安全 API 端点：

| 端点 | 方法 | 功能 | 权限验证 |
|------|------|------|----------|
| `/api/files/<int:file_id>` | GET | 获取文件信息 | ✅ user_id |
| `/api/files/<int:file_id>/download` | GET | 下载文件 | ✅ user_id |
| `/api/files/<int:file_id>` | DELETE | 删除文件(到回收站) | ✅ user_id |
| `/api/files/<int:file_id>/permanent_delete` | DELETE | 永久删除 | ✅ user_id + is_deleted |
| `/api/files/<int:file_id>/restore` | POST | 从回收站恢复 | ✅ user_id + is_deleted |
| `/api/files/<int:file_id>/rename` | PUT/PATCH | 重命名文件 | ✅ user_id |
| `/api/files/<int:file_id>/move` | PUT/PATCH | 移动文件 | ✅ user_id + 目标文件夹验证 |
| `/api/folders/<int:folder_id>` | GET | 获取文件夹信息 | ✅ user_id |
| `/api/folders/<int:folder_id>` | DELETE | 删除文件夹 | ✅ user_id + 递归验证 |
| `/api/folders/<int:folder_id>/rename` | PUT/PATCH | 重命名文件夹 | ✅ user_id |
| `/api/folders/<int:folder_id>/move` | PUT/PATCH | 移动文件夹 | ✅ user_id + 循环引用检查 |

## 安全测试用例

### 测试 1: 文件下载权限验证
```bash
# 攻击场景：用户A尝试下载用户B的文件
# 文件 ID: 123 (属于用户B)
# 用户A的认证信息

curl -X GET \
  http://localhost:5000/api/files/123/download \
  -H "Authorization: Basic $(echo -n 'userA:passwordA' | base64)"

# 预期结果: HTTP 404 或 403
# {"error": "File not found or access denied"}
```

### 测试 2: 文件夹删除权限验证
```bash
# 攻击场景：用户A尝试删除用户B的文件夹
# 文件夹 ID: 456 (属于用户B)

curl -X DELETE \
  http://localhost:5000/api/folders/456 \
  -H "Authorization: Basic $(echo -n 'userA:passwordA' | base64)"

# 预期结果: HTTP 404 或 403
# {"error": "Folder not found or access denied"}
```

### 测试 3: 递归操作权限验证
```bash
# 攻击场景：用户A在自己的文件夹中创建子文件夹，
# 然后尝试通过 move API 将其移动到用户B的文件夹中

curl -X PUT \
  http://localhost:5000/api/folders/789/move \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'userA:passwordA' | base64)" \
  -d '{"parent_id": 999}'  # 999 是用户B的文件夹

# 预期结果: HTTP 404
# {"error": "Target folder not found or access denied"}
```

### 测试 4: 回收站恢复权限验证
```bash
# 攻击场景：用户A尝试恢复用户B回收站中的文件
# 文件 ID: 100 (用户B已删除的文件)

curl -X POST \
  http://localhost:5000/api/files/100/restore \
  -H "Authorization: Basic $(echo -n 'userA:passwordA' | base64)"

# 预期结果: HTTP 404
# {"error": "File not found in trash or access denied"}
```

## 代码审查检查清单

- [x] 所有文件查询操作都包含 `user_id` 过滤
- [x] 所有文件夹查询操作都包含 `user_id` 过滤
- [x] 递归操作中子文件夹查询包含 `user_id` 过滤
- [x] 递归操作中子文件查询包含 `user_id` 过滤
- [x] 父文件夹查询包含 `user_id` 过滤
- [x] API 端点添加统一的所有权验证函数
- [x] 错误响应不泄露资源存在信息（返回 404 而不是 403）

## 安全加固建议

1. **日志记录**: 记录所有对非授权资源的访问尝试，用于审计和入侵检测
2. **速率限制**: 对 API 端点实施速率限制，防止暴力枚举文件ID
3. **ID 随机化**: 考虑使用不可预测的 UUID 替代自增ID
4. **定期审计**: 定期使用静态代码分析工具检查类似问题

## 修复验证结果

| 检查项 | 状态 |
|--------|------|
| 权限装饰器已添加 | ✅ |
| 辅助函数已添加 | ✅ |
| `delete_folder` 递归操作已修复 | ✅ |
| `restore_file` 父文件夹验证已修复 | ✅ |
| `restore_folder` 递归操作已修复 | ✅ |
| `batch_restore` 批量操作已修复 | ✅ |
| `batch_move` 循环检测已修复 | ✅ |
| `trash` 视图递归已修复 | ✅ |
| API 端点权限验证已添加 | ✅ |

## 总结

所有已识别的 IDOR 水平越权漏洞已修复。修复策略包括：

1. **统一权限验证层**: 新增装饰器和辅助函数，集中处理权限验证
2. **深度验证**: 不仅验证直接资源，还验证所有关联资源（父文件夹、子文件夹）
3. **最小权限原则**: 每个操作都验证用户只能访问自己的资源
4. **防御性编程**: 在递归操作中逐层验证权限，防止通过子资源绕过

修复后的代码确保用户只能访问、修改、删除自己拥有的文件和文件夹。
