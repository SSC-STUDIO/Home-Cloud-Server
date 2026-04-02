#!/bin/bash
# Home-Cloud-Server XSS漏洞修复脚本
# 执行此脚本自动应用安全修复

echo "=========================================="
echo "Home-Cloud-Server XSS漏洞修复脚本"
echo "=========================================="
echo ""

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "[1/5] 检查项目结构..."
if [ ! -f "$PROJECT_DIR/app/__init__.py" ]; then
    echo "错误: 未找到项目文件，请确保此脚本位于项目security_patches目录中"
    exit 1
fi
echo "  ✓ 项目结构检查通过"

echo ""
echo "[2/5] 应用highlightSearchMatches函数修复..."
JS_FILE="$PROJECT_DIR/app/static/js/files-index.js"
if [ -f "$JS_FILE" ]; then
    # 备份原文件
    cp "$JS_FILE" "$JS_FILE.backup.$(date +%Y%m%d%H%M%S)"
    echo "  ✓ 已备份原文件"
    
    # 这里使用sed或手动应用修复
    # 实际使用时建议使用patch命令
    echo "  ! 请手动应用security_patches/xss_fix_highlight.patch中的修复"
    echo "     或使用: patch -p1 < security_patches/xss_fix_highlight.patch"
else
    echo "  ✗ 未找到文件: $JS_FILE"
fi

echo ""
echo "[3/5] 添加安全中间件..."
MIDDLEWARE_FILE="$PROJECT_DIR/app/security_middleware.py"
if [ -f "$MIDDLEWARE_FILE" ]; then
    echo "  ✓ 安全中间件文件已存在"
else
    echo "  ✗ 安全中间件文件不存在，请手动复制"
fi

echo ""
echo "[4/5] 更新app/__init__.py..."
INIT_FILE="$PROJECT_DIR/app/__init__.py"
if [ -f "$INIT_FILE" ]; then
    # 检查是否已经添加了安全头
    if grep -q "add_security_headers" "$INIT_FILE"; then
        echo "  ✓ 安全头已配置"
    else
        echo "  ! 需要添加安全头配置到app/__init__.py"
        echo ""
        echo "    请在create_app函数中添加以下代码:"
        echo "    from app.security_middleware import init_security_headers"
        echo "    init_security_headers(app)"
    fi
else
    echo "  ✗ 未找到文件: $INIT_FILE"
fi

echo ""
echo "[5/5] 验证修复..."
echo ""
echo "修复完成后，请执行以下验证步骤:"
echo ""
echo "1. 检查安全头:"
echo "   curl -I http://localhost:5000/ | grep -E 'Content-Security-Policy|X-XSS-Protection'"
echo ""
echo "2. 测试XSS防护:"
echo "   在搜索框输入: <script>alert('XSS')</script>"
echo "   检查是否被转义显示"
echo ""
echo "3. 运行自动化测试:"
echo "   python3 xss_poc_and_fixes.md中的测试脚本"
echo ""

echo "=========================================="
echo "修复指南"
echo "=========================================="
echo ""
echo "【立即修复】(1小时内完成)"
echo "─────────────────────────────────────────"
echo "1. 修复highlightSearchMatches函数 (高危)"
echo "   文件: app/static/js/files-index.js"
echo "   操作: 使用DOM API替代innerHTML"
echo ""
echo "2. 添加安全中间件"
echo "   文件: app/security_middleware.py (已创建)"
echo "   操作: 在app/__init__.py中导入并初始化"
echo ""
echo "【短期修复】(24小时内完成)"
echo "─────────────────────────────────────────"
echo "3. 添加DOMPurify库"
echo "   在base.html中添加:"
echo "   <script src='https://cdnjs.cloudflare.com/ajax/libs/dompurify/3.0.6/purify.min.js'></script>"
echo ""
echo "4. 更新模板增强转义"
echo "   在_item_rows.html中使用显式转义:"
echo "   data-folder-name=\"{{ folder.name|e }}\""
echo ""
echo "【长期改进】(1周内完成)"
echo "─────────────────────────────────────────"
echo "5. 集成自动化安全测试到CI/CD"
echo "6. 定期进行渗透测试"
echo "7. 对开发人员进行安全培训"
echo ""
echo "=========================================="
