#!/bin/bash
# ============================================
# 智能股票分析 PWA - 阿里云 ECS 一键部署脚本
# 系统要求: Ubuntu 22.04 / CentOS 8+
# 用法: sudo bash deploy.sh
# ============================================

set -e

echo "=========================================="
echo "  智能股票分析 PWA - 开始部署"
echo "=========================================="

# 检测系统类型
if [ -f /etc/debian_version ]; then
    OS="debian"
    echo "检测到 Ubuntu/Debian 系统"
elif [ -f /etc/redhat-release ]; then
    OS="redhat"
    echo "检测到 CentOS/RHEL 系统"
else
    echo "不支持的系统，请使用 Ubuntu 22.04 或 CentOS 8+"
    exit 1
fi

# ===== 1. 安装系统依赖 =====
echo ""
echo "[1/6] 安装系统依赖..."
if [ "$OS" = "debian" ]; then
    apt update -y
    apt install -y python3 python3-pip python3-venv git nginx
else
    yum install -y python3 python3-pip git nginx
fi

# ===== 2. 拉取代码 =====
echo ""
echo "[2/6] 拉取项目代码..."
APP_DIR="/opt/stock-analyzer"
if [ -d "$APP_DIR" ]; then
    cd "$APP_DIR"
    git pull origin main
else
    git clone https://github.com/zhengdafu86/stock-analyzer.git "$APP_DIR"
    cd "$APP_DIR"
fi

# ===== 3. 创建虚拟环境并安装依赖 =====
echo ""
echo "[3/6] 安装 Python 依赖..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn

# ===== 4. 配置 systemd 服务（开机自启） =====
echo ""
echo "[4/6] 配置系统服务..."
cat > /etc/systemd/system/stock-analyzer.service << 'EOF'
[Unit]
Description=Stock Analyzer PWA
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/stock-analyzer
Environment=AI_PROVIDER=none
ExecStart=/opt/stock-analyzer/venv/bin/gunicorn app:app --bind 127.0.0.1:5000 --workers 2 --timeout 120
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable stock-analyzer
systemctl restart stock-analyzer

# ===== 5. 配置 Nginx 反向代理 =====
echo ""
echo "[5/6] 配置 Nginx..."
cat > /etc/nginx/conf.d/stock-analyzer.conf << 'EOF'
server {
    listen 80;
    server_name _;

    location /static/ {
        alias /opt/stock-analyzer/static/;
        expires 7d;
    }

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_connect_timeout 30;
        proxy_read_timeout 120;
    }
}
EOF

# 删除默认站点（如果有）
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

# ===== 6. 完成 =====
echo ""
echo "=========================================="
echo "  部署完成！"
echo "=========================================="

# 获取服务器公网 IP
PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || echo "你的服务器IP")

echo ""
echo "  访问地址: http://${PUBLIC_IP}"
echo ""
echo "  常用命令:"
echo "    查看状态: systemctl status stock-analyzer"
echo "    查看日志: journalctl -u stock-analyzer -f"
echo "    重启服务: systemctl restart stock-analyzer"
echo "    更新代码: cd /opt/stock-analyzer && git pull && systemctl restart stock-analyzer"
echo ""
echo "  把上面的访问地址发给朋友就能用了！"
echo "=========================================="
