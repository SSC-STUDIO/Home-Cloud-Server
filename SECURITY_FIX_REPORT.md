# 输入验证与路径安全 - 中危漏洞修复报告

**修复日期**: 2026-04-02  
**修复人员**: 安全修复脚本  
**漏洞等级**: 中危  
**漏洞数量**: 4个

---

## 修复的漏洞列表

### 漏洞1: 目录访问 - 路径验证不完整

**漏洞描述**:  
文件路径验证不够严格，可能导致目录遍历攻击，攻击者可能通过构造特殊路径访问系统敏感文件。

**影响范围**:
- 文件上传功能
- 文件下载功能
- 文件夹操作

**修复措施**:
1. 创建 `PathValidator` 类，提供严格的路径验证
2. 扩展危险路径模式检测列表
3. 使用 `os.path.commonpath()` 确保路径在允许的基目录下
4. 规范化所有输入路径

**代码变更**:
```python
# 新增路径验证
class PathValidator:
    MAX_PATH_LENGTH = 4096
    DANGEROUS_PATTERNS = [
        '../', '..\\', '/..', '\\..',
        '..%2f', '..%2F', '%2e%2e', '%252e%252e',
        '....', '.....', '....\\',
        '%2e%2e%2f', '%252e%252e%252f',
    ]
    
    @classmethod
    def validate_path(cls, path: str, base_dir: str = None) -> Optional[str]:
        # 实现路径验证逻辑
```

---

### 漏洞2: 文件名验证 - 缺少魔术字节检查

**漏洞描述**:  
系统仅通过文件扩展名验证文件类型，攻击者可以伪造文件扩展名上传恶意文件。

**影响范围**:
- 文件上传功能
- 远程文件下载功能

**修复措施**:
1. 创建 `MagicBytesValidator` 类，实现文件魔术字节检查
2. 定义常见文件类型的魔术字节签名
3. 提供文件真实类型检测功能
4. 建立危险文件类型黑名单

**代码变更**:
```python
# 新增魔术字节验证
class MagicBytesValidator:
    MAGIC_BYTES = {
        'image/jpeg': [(b'\xff\xd8\xff', None)],
        'image/png': [(b'\x89PNG\r\n\x1a\n', None)],
        'application/pdf': [(b'%PDF', None)],
        # ... 更多类型
    }
    
    @classmethod
    def validate_file_type(cls, file_path: str, allowed_types: set = None):
        # 实现魔术字节检查
```

---

### 漏洞3: 输入长度限制 - 未设置最大长度

**漏洞描述**:  
多个输入字段未设置长度限制，可能导致缓冲区溢出、拒绝服务攻击或数据库性能问题。

**影响范围**:
- 文件名输入
- 文件夹名输入
- 搜索查询
- URL输入

**修复措施**:
1. 创建 `InputLengthValidator` 类，统一长度验证
2. 为不同类型的输入定义长度限制
3. 在关键函数中添加长度检查
4. 更新 `normalize_item_name()` 等函数

**代码变更**:
```python
# 新增输入长度验证
class InputLengthValidator:
    LIMITS = {
        'filename': 255,
        'folder_name': 255,
        'search_query': 200,
        'url': 2048,
        'file_path': 4096,
    }
    
    @classmethod
    def validate(cls, input_value: str, field_type: str) -> Tuple[bool, str]:
        max_length = cls.LIMITS.get(field_type, 255)
        if len(input_value) > max_length:
            return False, f"输入太长 (最大 {max_length} 字符)"
```

---

### 漏洞4: 特殊字符过滤 - 过滤不完全

**漏洞描述**:  
特殊字符过滤不完整，可能导致XSS攻击、脚本注入或其他安全问题。

**影响范围**:
- 所有用户输入字段
- 文件名显示
- 搜索结果显示

**修复措施**:
1. 创建 `SpecialCharFilter` 类，完善特殊字符过滤
2. 定义控制字符、危险Unicode字符集合
3. 实现脚本注入、SQL注入、命令注入检测
4. 提供文本清理和HTML转义功能

**代码变更**:
```python
# 新增特殊字符过滤
class SpecialCharFilter:
    CONTROL_CHARS = frozenset(chr(i) for i in range(0x20)) | {'\x7f'}
    DANGEROUS_UNICODE = {'\ufeff', '\u200b', '\u200c', '\u200d'}
    
    SCRIPT_PATTERNS = [
        r'<\s*script[^>]*>.*?<\s*/\s*script\s*>',
        r'javascript\s*:',
        r'on\w+\s*=',
    ]
    
    @classmethod
    def has_script_content(cls, text: str) -> bool:
        # 检测脚本注入
```

---

## 新增/修改的文件

| 文件路径 | 操作类型 | 说明 |
|---------|---------|------|
| `app/utils/security_validation.py` | 新增 | 统一安全验证模块 |
| `app/utils/file_utils.py` | 修改 | 集成安全验证 |
| `app/routes/files.py` | 修改 | 强化输入验证 |
| `app/security_middleware.py` | 修改 | 安全中间件 |

---

## 修复验证清单

- [x] 创建安全输入验证模块
- [x] 更新文件工具函数
- [x] 更新文件路由
- [x] 更新安全中间件
- [x] 添加路径验证
- [x] 添加魔术字节检查
- [x] 添加长度限制
- [x] 完善特殊字符过滤

---

## 测试建议

1. **路径遍历测试**:
   ```bash
   # 测试路径遍历防护
   curl -X POST "http://localhost/files/upload"      -F "files[]=@test.txt"      -F "filename=../../../etc/passwd"
   ```

2. **文件类型欺骗测试**:
   ```bash
   # 测试魔术字节检查
   # 创建一个伪装成.jpg的.php文件并尝试上传
   echo '<?php phpinfo(); ?>' > test.jpg
   curl -X POST "http://localhost/files/upload" -F "files[]=@test.jpg"
   ```

3. **长度限制测试**:
   ```bash
   # 测试超长输入
   python3 -c "print('A'*300)" | xargs -I {}      curl "http://localhost/files/search?query={}"
   ```

4. **特殊字符测试**:
   ```bash
   # 测试XSS防护
   curl -X POST "http://localhost/folders/create"      -d "folder_name=<script>alert(1)</script>"
   ```

---

## 后续建议

1. **定期安全审计**: 建议每季度进行一次安全代码审计
2. **自动化测试**: 集成安全测试到CI/CD流程
3. **监控告警**: 对异常输入模式进行监控和告警
4. **更新依赖**: 及时更新安全相关依赖库
5. **培训**: 对开发人员进行安全编码培训

---

*报告生成时间: 2026-04-02*  
*分类: 内部机密*
