# 安全修复提交指南

## 修复内容总结

我修复了 Home-Cloud-Server 中的 **5 个严重安全漏洞**：

### 🚨 高危漏洞

1. **路径遍历漏洞 (Path Traversal)**
   - 攻击者可通过构造特殊文件名访问系统任意文件
   - 例如：`../../../etc/passwd` 或 `file%00.txt`

2. **缺失 CSRF 保护**
   - 攻击者可在恶意网站诱导用户执行敏感操作
   - 如：删除文件、修改密码等

3. **密码重置功能失效**
   - 任何人可重置任意用户密码
   - 重置令牌未验证，接受任意值

### ⚠️ 中危漏洞

4. **文件上传竞态条件**
   - 并发上传可能导致文件覆盖或重复

5. **API 路径遍历**
   - API 文件上传未验证文件名

---

## 如何提交 PR

### 方法 1：Fork 后提交 (推荐)

1. 访问 https://github.com/SSC-STUDIO/Home-Cloud-Server
2. 点击右上角的 **Fork** 按钮
3. 克隆你的 Fork 到本地：
```bash
git clone https://github.com/YOUR_USERNAME/Home-Cloud-Server.git
cd Home-Cloud-Server
```

4. 添加本仓库为上游：
```bash
git remote add upstream https://github.com/SSC-STUDIO/Home-Cloud-Server.git
```

5. 复制我的修复文件：
```bash
# 从当前机器复制修改后的文件，或手动复制以下内容
```

6. 提交并推送：
```bash
git checkout -b security-fixes
git add -A
git commit -m "Security fixes: Path traversal, CSRF protection, password reset, race conditions"
git push origin security-fixes
```

7. 在 GitHub 上创建 Pull Request

---

## 修复详情

### 1. 修复路径遍历 (app/routes/files.py)

**原始代码漏洞：**
```python
def normalize_item_name(raw_value):
    # 只检查了 / 和 \
    if any(separator in value for separator in ('/', '\\')):
        return None
```

**修复后代码：**
```python
def normalize_item_name(raw_value):
    # 增加了以下检查：
    # - Null 字节注入
    # - Unicode 规范化 (防止同形字攻击)
    # - 路径遍历模式 (../, ..%2f 等)
    # - Windows 保留名称 (CON, PRN 等)
    # - 绝对路径检查
```

### 2. 添加 CSRF 保护

**新增依赖：**
```
Flask-WTF>=1.2.0
```

**初始化：**
```python
from flask_wtf.csrf import CSRFProtect
csrf = CSRFProtect()
csrf.init_app(app)
```

### 3. 修复密码重置

**User 模型新增字段：**
```python
reset_token = db.Column(db.String(64), nullable=True)
reset_token_expires = db.Column(db.DateTime, nullable=True)
```

**新增方法：**
- `generate_reset_token()` - 生成带过期时间的令牌
- `verify_reset_token()` - 验证令牌有效性
- `clear_reset_token()` - 使用后清除

### 4. 修复竞态条件

**新函数：**
```python
def generate_unique_filename(user_id, folder_id, filename):
    # 使用数据库行锁确保原子性
    # 防止并发上传冲突
```

---

## 测试建议

### 测试路径遍历防护
```bash
# 应被拒绝的上传文件名示例
curl -X POST -F "file=@test.txt;filename=../../../etc/passwd" ...
curl -X POST -F "file=@test.txt;filename=file%00.txt" ...
curl -X POST -F "file=@test.txt;filename=CON" ...
```

### 测试 CSRF 保护
```bash
# 无 CSRF token 的请求应被拒绝
curl -X POST http://localhost:5000/files/upload ...
```

### 测试密码重置
1. 请求重置密码
2. 等待 1 小时以上
3. 尝试使用过期链接 → 应失败

---

## 修改的文件

1. `requirements.txt` - 添加 Flask-WTF
2. `app/__init__.py` - 初始化 CSRF
3. `app/models/user.py` - 密码重置字段和方法
4. `app/routes/auth.py` - 修复密码重置逻辑
5. `app/routes/files.py` - 路径遍历和竞态条件修复
6. `app/routes/api.py` - API CSRF 豁免和文件名验证

---

## PR 标题建议

```
Security: Fix critical vulnerabilities (Path Traversal, CSRF, Password Reset, Race Conditions)
```

## PR 描述建议

```markdown
## Summary
This PR fixes 5 security vulnerabilities discovered in the codebase:

### Changes
- **Path Traversal**: Enhanced `normalize_item_name()` to prevent bypasses
- **CSRF Protection**: Added Flask-WTF CSRF protection to all web routes
- **Password Reset**: Fixed broken reset functionality with proper token validation
- **Race Condition**: Used database locking for atomic filename generation
- **API Security**: Added filename validation to API uploads

### Testing
- Path traversal payloads are rejected
- CSRF tokens required for web routes
- API routes exempt (use Basic Auth)
- Password reset tokens expire after 1 hour

### Migration Required
New columns in `users` table:
- `reset_token` (String, nullable)
- `reset_token_expires` (DateTime, nullable)
```

---

## 提交后的 Git 命令参考

```bash
# 查看当前分支
git branch

# 查看修改状态
git status

# 查看提交历史
git log --oneline -5

# 推送到你的 Fork
git push origin security-fixes
```

然后访问你的 GitHub Fork 页面，点击 "Compare & pull request" 按钮。