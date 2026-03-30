#!/bin/bash
# 推送到原始仓库并创建 PR 的脚本

cd /root/.openclaw/workspace/Home-Cloud-Server

echo "=== 推送到原始仓库 ==="

# 推送 security-fixes 分支到 origin
git push origin security-fixes

echo ""
echo "=== 推送完成 ==="
echo ""
echo "现在请在浏览器中访问："
echo "https://github.com/SSC-STUDIO/Home-Cloud-Server/compare/master...security-fixes"
echo ""
echo "点击 'Create pull request' 按钮创建 PR"
