"""
会话安全漏洞修复验证报告
生成时间: 2026-04-02
"""

import os
import sys

project_root = os.path.dirname(os.path.abspath(__file__))

def check_file_contains(filepath, patterns, description):
    """检查文件是否包含指定模式"""
    full_path = os.path.join(project_root, filepath)
    if not os.path.exists(full_path):
        return False, f"文件不存在: {filepath}"
    
    with open(full_path, 'r') as f:
        content = f.read()
    
    missing = []
    for pattern in patterns:
        if pattern not in content:
            missing.append(pattern)
    
    if missing:
        return False, f"缺少: {', '.join(missing[:3])}..."
    return True, "检查通过"

def verify_fixes():
    """验证所有修复"""
    results = []
    
    print("=" * 70)
    print("会话安全漏洞修复验证报告")
    print("=" * 70)
    
    # ========================================================================
    # 修复1: 会话Cookie安全
    # ========================================================================
    print("\n🔒 漏洞 #1: 会话Cookie安全 - Secure/HttpOnly/SameSite")
    print("-" * 70)
    
    checks = [
        ("config.py", ["SESSION_COOKIE_SECURE", "SESSION_COOKIE_HTTPONLY", "SESSION_COOKIE_SAMESITE"]),
        ("config.py", ["SESSION_COOKIE_NAME", "PERMANENT_SESSION_LIFETIME"]),
    ]
    
    all_pass = True
    for filepath, patterns in checks:
        passed, msg = check_file_contains(filepath, patterns, "")
        status = "✅" if passed else "❌"
        print(f"  {status} {filepath}: {msg}")
        all_pass = all_pass and passed
    
    results.append(("会话Cookie安全", all_pass))
    
    # ========================================================================
    # 修复2: 并发登录检测
    # ========================================================================
    print("\n🔒 漏洞 #2: 会话验证 - 并发登录检测")
    print("-" * 70)
    
    checks = [
        ("app/models/user_session.py", ["class UserSession", "session_token", "validate_session"]),
        ("config.py", ["CONCURRENT_LOGIN_DETECTION", "ALLOW_MULTIPLE_SESSIONS", "SESSION_EXPIRE_HOURS"]),
        ("app/models/__init__.py", ["UserSession"]),
        ("app/models/db_init.py", ["UserSession"]),
    ]
    
    all_pass = True
    for filepath, patterns in checks:
        passed, msg = check_file_contains(filepath, patterns, "")
        status = "✅" if passed else "❌"
        print(f"  {status} {filepath}: {msg}")
        all_pass = all_pass and passed
    
    results.append(("并发登录检测", all_pass))
    
    # ========================================================================
    # 修复3: 会话固定攻击
    # ========================================================================
    print("\n🔒 漏洞 #3: 会话固定攻击 - 登录后重新生成session ID")
    print("-" * 70)
    
    checks = [
        ("app/routes/auth.py", ["session.clear()", "session.permanent = True", "session_token"]),
        ("app/__init__.py", ["from flask_session import Session", "session_manager"]),
    ]
    
    all_pass = True
    for filepath, patterns in checks:
        passed, msg = check_file_contains(filepath, patterns, "")
        status = "✅" if passed else "❌"
        print(f"  {status} {filepath}: {msg}")
        all_pass = all_pass and passed
    
    results.append(("会话固定攻击修复", all_pass))
    
    # ========================================================================
    # 修复4: Token日志泄露
    # ========================================================================
    print("\n🔒 漏洞 #4: Token日志泄露 - 敏感信息记录到日志")
    print("-" * 70)
    
    checks = [
        ("app/utils/security_logger.py", ["class SensitiveDataMasker", "mask_string", "JWT_TOKEN"]),
        ("app/routes/auth.py", ["SensitiveDataMasker"]),
        ("app/routes/api.py", ["SensitiveDataMasker"]),
    ]
    
    all_pass = True
    for filepath, patterns in checks:
        passed, msg = check_file_contains(filepath, patterns, "")
        status = "✅" if passed else "❌"
        print(f"  {status} {filepath}: {msg}")
        all_pass = all_pass and passed
    
    results.append(("Token日志泄露修复", all_pass))
    
    # ========================================================================
    # 其他检查
    # ========================================================================
    print("\n📦 依赖和迁移")
    print("-" * 70)
    
    checks = [
        ("requirements.txt", ["Flask-Session"]),
        ("migrate_add_user_session.py", ["UserSession", "user_sessions"]),
    ]
    
    all_pass = True
    for filepath, patterns in checks:
        passed, msg = check_file_contains(filepath, patterns, "")
        status = "✅" if passed else "❌"
        print(f"  {status} {filepath}: {msg}")
        all_pass = all_pass and passed
    
    results.append(("依赖和迁移", all_pass))
    
    # ========================================================================
    # 总结
    # ========================================================================
    print("\n" + "=" * 70)
    print("修复总结")
    print("=" * 70)
    
    for name, passed in results:
        status = "✅ 已修复" if passed else "❌ 需要检查"
        print(f"  {status}: {name}")
    
    all_passed = all(r[1] for r in results)
    
    print("\n" + "=" * 70)
    print("新增/修改的文件列表")
    print("=" * 70)
    
    files = [
        ("config.py", "添加Session安全配置"),
        ("app/__init__.py", "初始化Flask-Session和安全检查"),
        ("app/routes/auth.py", "修复会话固定和并发登录"),
        ("app/routes/api.py", "添加日志脱敏"),
        ("app/models/user_session.py", "新增用户会话模型"),
        ("app/models/__init__.py", "导出UserSession"),
        ("app/models/db_init.py", "导入UserSession"),
        ("app/utils/security_logger.py", "新增敏感日志脱敏工具"),
        ("requirements.txt", "添加Flask-Session依赖"),
        ("migrate_add_user_session.py", "数据库迁移脚本"),
    ]
    
    for filepath, desc in files:
        full_path = os.path.join(project_root, filepath)
        exists = "✅" if os.path.exists(full_path) else "❌"
        print(f"  {exists} {filepath}")
        print(f"      └─ {desc}")
    
    print("\n" + "=" * 70)
    print("部署说明")
    print("=" * 70)
    print("""
1. 安装依赖:
   pip install -r requirements.txt

2. 运行数据库迁移:
   python migrate_add_user_session.py

3. 配置环境变量(可选):
   export SESSION_COOKIE_SECURE=True
   export SESSION_COOKIE_HTTPONLY=True
   export SESSION_COOKIE_SAMESITE=Lax
   export CONCURRENT_LOGIN_DETECTION=True
   export ALLOW_MULTIPLE_SESSIONS=False

4. 重启应用

5. 验证修复:
   - 登录后检查浏览器cookie是否设置了HttpOnly和Secure标志
   - 尝试使用旧session ID访问，应被重定向到登录页面
   - 检查日志中敏感信息是否被脱敏
   - 尝试并发登录，根据配置旧会话应失效
""")
    print("=" * 70)
    
    return all_passed

if __name__ == '__main__':
    success = verify_fixes()
    sys.exit(0 if success else 1)
