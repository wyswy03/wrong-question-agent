#!/bin/bash
# 在 Ubuntu 22.04 / 24.04 轻量服务器上安装错题本。用 root 执行。
set -euo pipefail

APP=/opt/wrong-question-agent
DATA=/var/lib/wrong-question
SRC_DIR="${1:-}"

if [[ -z "$SRC_DIR" ]]; then
  echo "用法: sudo bash install.sh /path/to/WrongQuestionAgent"
  echo "先把项目目录上传到服务器，再执行本脚本。"
  exit 1
fi

if [[ ! -f "$SRC_DIR/server.py" ]]; then
  echo "未找到 $SRC_DIR/server.py"
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 nginx

mkdir -p "$APP" "$DATA"
cp -a "$SRC_DIR/server.py" "$SRC_DIR/bank.py" "$SRC_DIR/ocr.py" "$SRC_DIR/web" "$APP/"
apt-get install -y python3-pip
pip3 install -r "$SRC_DIR/requirements.txt"
chown -R www-data:www-data "$APP" "$DATA"

install -m 644 "$SRC_DIR/deploy/wrong-question.service" /etc/systemd/system/wrong-question.service
install -m 644 "$SRC_DIR/deploy/nginx.conf" /etc/nginx/sites-available/wrong-question
ln -sfn /etc/nginx/sites-available/wrong-question /etc/nginx/sites-enabled/wrong-question
rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl daemon-reload
systemctl enable --now wrong-question
systemctl reload nginx

IP=$(curl -s --max-time 5 ifconfig.me || hostname -I | awk '{print $1}')
echo
echo "安装完成。浏览器打开: http://$IP"
echo "安全组 / 防火墙请放行 80 端口。"
echo "有域名后，可用: sudo apt-get install -y certbot python3-certbot-nginx && sudo certbot --nginx"
echo "手机摄像头需要 https；没有证书时请用「上传照片」。"
