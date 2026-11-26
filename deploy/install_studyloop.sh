#!/usr/bin/env bash
# StudyLoop installer for Debian 12 / Ubuntu 22.04+.
# Put the source at /opt/studyloop first, then run as root:
#   bash deploy/install_studyloop.sh
#
# It creates a separate systemd service and an Nginx site on 8081. It does not
# modify the existing blog (443 / 4000) or the previous StudyNotes service
# (8080 / 8010).
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/studyloop}"
NGINX_PORT="${NGINX_PORT:-8081}"
WEB_PORT="${WEB_PORT:-8011}"
PUBLIC_HOST="${PUBLIC_HOST:-8.137.166.186}"

if [ ! -f "$APP_DIR/manage.py" ]; then
  echo "未找到 $APP_DIR/manage.py。请先把 study-plan-community 源码复制到 $APP_DIR。" >&2
  exit 1
fi

cd "$APP_DIR"

echo "==> 检查 Python 版本"
python3 --version
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "==> 迁移数据库与收集静态文件"
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py collectstatic --noinput

if [ "${SEED_DEMO:-0}" = "1" ]; then
  echo "==> 写入演示数据"
  .venv/bin/python manage.py seed_demo
fi

mkdir -p media staticfiles
chown -R www-data:www-data "$APP_DIR"

echo "==> 安装 systemd 服务"
install -m 0644 deploy/studyloop.service /etc/systemd/system/studyloop.service
systemctl daemon-reload
systemctl enable studyloop
systemctl restart studyloop

echo "==> 安装 Nginx 站点（端口 $NGINX_PORT）"
install -m 0644 deploy/nginx-studyloop.conf /etc/nginx/sites-available/studyloop
ln -sfn /etc/nginx/sites-available/studyloop /etc/nginx/sites-enabled/studyloop
nginx -t
systemctl reload nginx

echo "==> 完成"
echo "请确认："
echo "  1. 云安全组放行 TCP $NGINX_PORT"
echo "  2. 如需本机防火墙：ufw allow $NGINX_PORT/tcp"
echo "  3. 访问 http://$PUBLIC_HOST:$NGINX_PORT/"
echo "  4. 如域名变化，修改 /etc/systemd/system/studyloop.service 中的"
echo "     DJANGO_ALLOWED_HOSTS 与 DJANGO_CSRF_TRUSTED_ORIGINS 后重启 studyloop"
