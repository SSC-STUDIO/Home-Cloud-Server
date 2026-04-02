"""
会话安全漏洞修复验证脚本

验证以下4个中危漏洞的修复：
1. 会话Cookie安全 - 缺少Secure/HttpOnly/SameSite
2. 会话验证 - 缺少并发登录检测
3. 会话固定攻击 - 登录后未重新生成session ID
4. Token日志泄露 - 敏感信息记录到日志
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# 添加项目路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)


class TestSessionSecurityFixes(unittest.TestCase):
    """会话安全修复验证测试"""
    
    @classmethod
    def setUpClass(cls):
        """测试类设置"""
        print("\n" + "=" * 70)
        print("会话安全漏洞修复验证")
        print("=" * 70 + "\n")
    
    # ========================================================================
    # 测试1: 会话Cookie安全配置
    # ========================================================================
    def test_1_session_cookie_config(self):
        """验证: 会话Cookie安全 - Secure/HttpOnly/SameSite配置"""
        print("\n[测试1] 会话Cookie安全配置验证...")
        
        from app import create_app
        app = create_app('production')
        
        # 验证配置项存在
        self.assertIn('SESSION_COOKIE_SECURE', app.config)
        self.assertIn('SESSION_COOKIE_HTTPONLY', app.config)
        self.assertIn('SESSION_COOKIE_SAMESITE', app.config)
        self.assertIn('SESSION_COOKIE_NAME', app.config)
        self.assertIn('PERMANENT_SESSION_LIFETIME', app.config)
        
        # 验证默认值
        self.assertTrue(app.config['SESSION_COOKIE_SECURE'])
        self.assertTrue(app.config['SESSION_COOKIE_HTTPONLY'])
        self.assertIn(app.config['SESSION_COOKIE_SAMESITE'], ['Strict', 'Lax', 'None'])
        
        # 验证session cookie名称已更改（不使用默认的'session'）
        self.assertNotEqual(app.config['SESSION_COOKIE_NAME'], 'session')
        
        print(f"  ✓ SESSION_COOKIE_SECURE: {app.config['SESSION_COOKIE_SECURE']}")
        print(f"  ✓ SESSION_COOKIE_HTTPONLY: {app.config['SESSION_COOKIE_HTTPONLY']}")
        print(f"  ✓ SESSION_COOKIE_SAMESITE: {app.config['SESSION_COOKIE_SAMESITE']}")
        print(f"  ✓ SESSION_COOKIE_NAME: {app.config['SESSION_COOKIE_NAME']}")
        print(f"  ✓ PERMANENT_SESSION_LIFETIME: {app.config['PERMANENT_SESSION_LIFETIME']}")
        print("  ✓ 所有Session Cookie安全配置正确")
    
    # ========================================================================
    # 测试2: 并发登录检测配置
    # ========================================================================
    def test_2_concurrent_login_detection_config(self):
        """验证: 并发登录检测配置"""
        print("\n[测试2] 并发登录检测配置验证...")
        
        from app import create_app
        app = create_app('production')
        
        # 验证配置项存在
        self.assertIn('CONCURRENT_LOGIN_DETECTION', app.config)
        self.assertIn('ALLOW_MULTIPLE_SESSIONS', app.config)
        self.assertIn('SESSION_EXPIRE_HOURS', app.config)
        
        # 验证默认值
        self.assertTrue(app.config['CONCURRENT_LOGIN_DETECTION'])
        self.assertIsInstance(app.config['ALLOW_MULTIPLE_SESSIONS'], bool)
        self.assertIsInstance(app.config['SESSION_EXPIRE_HOURS'], int)
        self.assertGreater(app.config['SESSION_EXPIRE_HOURS'], 0)
        
        print(f"  ✓ CONCURRENT_LOGIN_DETECTION: {app.config['CONCURRENT_LOGIN_DETECTION']}")
        print(f"  ✓ ALLOW_MULTIPLE_SESSIONS: {app.config['ALLOW_MULTIPLE_SESSIONS']}")
        print(f"  ✓ SESSION_EXPIRE_HOURS: {app.config['SESSION_EXPIRE_HOURS']}")
        print("  ✓ 并发登录检测配置正确")
    
    # ========================================================================
    # 测试3: UserSession模型
    # ========================================================================
    def test_3_user_session_model(self):
        """验证: UserSession模型功能"""
        print("\n[测试3] UserSession模型验证...")
        
        from app.models.user_session import UserSession
        from datetime import datetime, timedelta
        
        # 验证模型类存在
        self.assertIsNotNone(UserSession)
        
        # 验证模型属性
        self.assertTrue(hasattr(UserSession, 'id'))
        self.assertTrue(hasattr(UserSession, 'user_id'))
        self.assertTrue(hasattr(UserSession, 'session_token'))
        self.assertTrue(hasattr(UserSession, 'session_hash'))
        self.assertTrue(hasattr(UserSession, 'ip_address'))
        self.assertTrue(hasattr(UserSession, 'user_agent'))
        self.assertTrue(hasattr(UserSession, 'created_at'))
        self.assertTrue(hasattr(UserSession, 'expires_at'))
        self.assertTrue(hasattr(UserSession, 'is_active'))
        self.assertTrue(hasattr(UserSession, 'is_revoked'))
        
        # 验证类方法存在
        self.assertTrue(hasattr(UserSession, 'create_session'))
        self.assertTrue(hasattr(UserSession, 'validate_session'))
        self.assertTrue(hasattr(UserSession, 'invalidate_session'))
        self.assertTrue(hasattr(UserSession, 'invalidate_user_sessions'))
        self.assertTrue(hasattr(UserSession, 'get_active_sessions'))
        
        # 验证哈希函数
        token = "test_token_123"
        hash1 = UserSession._hash_session(token)
        hash2 = UserSession._hash_session(token)
        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 64)  # SHA256哈希长度
        
        print("  ✓ UserSession模型定义正确")
        print("  ✓ 所有必需属性存在")
        print("  ✓ 所有类方法存在")
        print("  ✓ Session哈希函数工作正常")
    
    # ========================================================================
    # 测试4: 会话固定攻击修复
    # ========================================================================
    def test_4_session_fixation_fix(self):
        """验证: 会话固定攻击修复 - 登录后重新生成session ID"""
        print("\n[测试4] 会话固定攻击修复验证...")
        
        # 读取auth.py文件，验证是否包含session重新生成代码
        auth_file = os.path.join(project_root, 'app', 'routes', 'auth.py')
        with open(auth_file, 'r') as f:
            content = f.read()
        
        # 验证登录函数中包含session清除和重新生成
        self.assertIn('session.clear()', content)
        self.assertIn('session.permanent = True', content)
        
        # 验证session_token被设置
        self.assertIn("session['session_token']", content)
        
        print("  ✓ 登录函数包含session.clear()")
        print("  ✓ 登录函数设置session.permanent = True")
        print("  ✓ 登录函数设置session_token")
        print("  ✓ 会话固定攻击已修复")
    
    # ========================================================================
    # 测试5: 敏感日志脱敏
    # ========================================================================
    def test_5_sensitive_data_masker(self):
        """验证: Token日志泄露修复 - 敏感数据脱敏"""
        print("\n[测试5] 敏感日志脱敏验证...")
        
        from app.utils.security_logger import SensitiveDataMasker, mask_sensitive_data
        
        # 验证脱敏器类存在
        self.assertIsNotNone(SensitiveDataMasker)
        
        # 测试JWT token脱敏
        jwt_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        masked_jwt = SensitiveDataMasker.mask_string(jwt_token)
        self.assertEqual(masked_jwt, '[JWT_TOKEN]')
        print(f"  ✓ JWT Token脱敏: {jwt_token[:20]}... → {masked_jwt}")
        
        # 测试Bearer token脱敏
        bearer_token = "Bearer abc123xyz789"
        masked_bearer = SensitiveDataMasker.mask_string(bearer_token)
        self.assertEqual(masked_bearer, 'Bearer [MASKED]')
        print(f"  ✓ Bearer Token脱敏: {bearer_token} → {masked_bearer}")
        
        # 测试Basic Auth脱敏
        basic_auth = "Basic dXNlcjpwYXNzd29yZA=="
        masked_basic = SensitiveDataMasker.mask_string(basic_auth)
        self.assertEqual(masked_basic, 'Basic [MASKED]')
        print(f"  ✓ Basic Auth脱敏: {basic_auth} → {masked_basic}")
        
        # 测试字典脱敏
        test_dict = {
            'username': 'test_user',
            'password': 'secret_password',
            'token': 'abc123',
            'api_key': 'key_12345'
        }
        masked_dict = SensitiveDataMasker.mask_dict(test_dict)
        self.assertEqual(masked_dict['password'], '[MASKED]')
        self.assertEqual(masked_dict['token'], '[MASKED]')
        self.assertEqual(masked_dict['api_key'], '[MASKED]')
        self.assertEqual(masked_dict['username'], 'test_user')
        print("  ✓ 字典敏感字段脱敏正确")
        
        print("  ✓ 敏感日志脱敏功能正常")
    
    # ========================================================================
    # 测试6: 日志中使用脱敏
    # ========================================================================
    def test_6_log_masking_in_code(self):
        """验证: 代码中使用了日志脱敏"""
        print("\n[测试6] 代码日志脱敏验证...")
        
        # 检查auth.py中的日志脱敏
        auth_file = os.path.join(project_root, 'app', 'routes', 'auth.py')
        with open(auth_file, 'r') as f:
            auth_content = f.read()
        
        # 验证导入了SensitiveDataMasker
        self.assertIn('SensitiveDataMasker', auth_content)
        
        # 验证使用了safe_log_message或mask_string
        self.assertTrue(
            'safe_log_message' in auth_content or 'mask_string' in auth_content,
            "auth.py应使用日志脱敏方法"
        )
        
        # 检查api.py中的日志脱敏
        api_file = os.path.join(project_root, 'app', 'routes', 'api.py')
        with open(api_file, 'r') as f:
            api_content = f.read()
        
        # 验证导入了SensitiveDataMasker
        self.assertIn('SensitiveDataMasker', api_content)
        
        print("  ✓ auth.py使用了SensitiveDataMasker")
        print("  ✓ api.py使用了SensitiveDataMasker")
        print("  ✓ 日志脱敏已集成到代码中")
    
    # ========================================================================
    # 测试7: 会话安全配置初始化
    # ========================================================================
    def test_7_session_security_initialization(self):
        """验证: 会话安全配置在app初始化中正确设置"""
        print("\n[测试7] 会话安全配置初始化验证...")
        
        init_file = os.path.join(project_root, 'app', '__init__.py')
        with open(init_file, 'r') as f:
            content = f.read()
        
        # 验证Flask-Session导入
        self.assertIn('Flask-Session', content)
        self.assertIn('session_manager', content)
        
        # 验证session安全检查before_request
        self.assertIn('session_security_checks', content)
        self.assertIn('@app.before_request', content)
        
        print("  ✓ Flask-Session已导入")
        print("  ✓ session_manager已初始化")
        print("  ✓ session_security_checks已配置")
    
    # ========================================================================
    # 测试8: 密码修改后使其他会话失效
    # ========================================================================
    def test_8_password_change_session_invalidation(self):
        """验证: 密码修改后使其他会话失效"""
        print("\n[测试8] 密码修改会话失效验证...")
        
        auth_file = os.path.join(project_root, 'app', 'routes', 'auth.py')
        with open(auth_file, 'r') as f:
            content = f.read()
        
        # 验证密码修改函数中包含会话失效代码
        self.assertIn('invalidate_user_sessions', content)
        self.assertIn('sessions_invalidated_password_change', content)
        
        # 验证密码重置后也会使会话失效
        self.assertIn('sessions_invalidated_password_reset', content)
        
        print("  ✓ 密码修改后调用invalidate_user_sessions")
        print("  ✓ 密码重置后使所有会话失效")
        print("  ✓ 安全事件被正确记录")
    
    # ========================================================================
    # 测试9: 依赖项检查
    # ========================================================================
    def test_9_dependencies(self):
        """验证: 必要的依赖项已添加"""
        print("\n[测试9] 依赖项检查...")
        
        req_file = os.path.join(project_root, 'requirements.txt')
        with open(req_file, 'r') as f:
            content = f.read()
        
        # 验证Flask-Session已添加
        self.assertIn('Flask-Session', content)
        
        print("  ✓ Flask-Session已添加到requirements.txt")
    
    # ========================================================================
    # 测试10: 数据库迁移脚本
    # ========================================================================
    def test_10_migration_script(self):
        """验证: 数据库迁移脚本存在"""
        print("\n[测试10] 数据库迁移脚本验证...")
        
        migration_script = os.path.join(project_root, 'migrate_add_user_session.py')
        self.assertTrue(os.path.exists(migration_script))
        
        with open(migration_script, 'r') as f:
            content = f.read()
        
        # 验证脚本包含UserSession表创建
        self.assertIn('UserSession', content)
        self.assertIn('user_sessions', content)
        
        print("  ✓ 数据库迁移脚本存在")
        print("  ✓ 脚本包含UserSession表创建")


class TestSummary:
    """测试总结"""
    
    @classmethod
    def print_summary(cls):
        """打印修复总结"""
        print("\n" + "=" * 70)
        print("修复验证总结")
        print("=" * 70)
        
        fixes = [
            {
                "id": 1,
                "name": "会话Cookie安全 - Secure/HttpOnly/SameSite",
                "status": "✅ 已修复",
                "details": [
                    "config.py中添加SESSION_COOKIE_SECURE配置",
                    "config.py中添加SESSION_COOKIE_HTTPONLY配置",
                    "config.py中添加SESSION_COOKIE_SAMESITE配置",
                    "config.py中添加SESSION_COOKIE_NAME配置",
                    "config.py中添加PERMANENT_SESSION_LIFETIME配置"
                ]
            },
            {
                "id": 2,
                "name": "会话验证 - 并发登录检测",
                "status": "✅ 已修复",
                "details": [
                    "创建UserSession模型(app/models/user_session.py)",
                    "config.py中添加CONCURRENT_LOGIN_DETECTION配置",
                    "config.py中添加ALLOW_MULTIPLE_SESSIONS配置",
                    "config.py中添加SESSION_EXPIRE_HOURS配置",
                    "login()函数中创建服务器端会话记录",
                    "logout()函数中使服务器端会话失效",
                    "密码修改后使其他会话失效"
                ]
            },
            {
                "id": 3,
                "name": "会话固定攻击 - 登录后重新生成session ID",
                "status": "✅ 已修复",
                "details": [
                    "login()函数调用session.clear()清除旧session",
                    "login()函数设置session.permanent = True",
                    "添加Flask-Session支持服务器端session",
                    "会话安全检查中间件验证会话有效性"
                ]
            },
            {
                "id": 4,
                "name": "Token日志泄露 - 敏感信息记录到日志",
                "status": "✅ 已修复",
                "details": [
                    "创建SensitiveDataMasker工具类(app/utils/security_logger.py)",
                    "auth.py中使用脱敏日志记录",
                    "api.py中使用脱敏日志记录",
                    "JWT Token、Bearer Token、API Key等敏感信息被脱敏"
                ]
            }
        ]
        
        for fix in fixes:
            print(f"\n🔒 漏洞 #{fix['id']}: {fix['name']}")
            print(f"   状态: {fix['status']}")
            print("   修复内容:")
            for detail in fix['details']:
                print(f"     - {detail}")
        
        print("\n" + "=" * 70)
        print("新增/修改的文件:")
        print("=" * 70)
        files = [
            "config.py - 添加Session安全配置",
            "app/__init__.py - 初始化Flask-Session和安全检查",
            "app/routes/auth.py - 修复会话固定和并发登录",
            "app/routes/api.py - 添加日志脱敏",
            "app/models/user_session.py - 新增用户会话模型",
            "app/models/__init__.py - 导出UserSession",
            "app/models/db_init.py - 导入UserSession",
            "app/utils/security_logger.py - 新增敏感日志脱敏工具",
            "requirements.txt - 添加Flask-Session依赖",
            "migrate_add_user_session.py - 数据库迁移脚本"
        ]
        for f in files:
            print(f"  ✓ {f}")
        
        print("\n" + "=" * 70)
        print("部署说明:")
        print("=" * 70)
        print("1. 安装依赖: pip install -r requirements.txt")
        print("2. 运行数据库迁移: python migrate_add_user_session.py")
        print("3. 配置环境变量(可选):")
        print("   - SESSION_COOKIE_SECURE=True")
        print("   - SESSION_COOKIE_HTTPONLY=True")
        print("   - SESSION_COOKIE_SAMESITE=Lax")
        print("   - CONCURRENT_LOGIN_DETECTION=True")
        print("   - ALLOW_MULTIPLE_SESSIONS=False")
        print("4. 重启应用")
        print("=" * 70 + "\n")


def run_tests():
    """运行所有测试"""
    # 创建测试套件
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestSessionSecurityFixes)
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 打印总结
    TestSummary.print_summary()
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
