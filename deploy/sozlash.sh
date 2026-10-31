#!/usr/bin/env bash
# Serverni bir marta sozlash (Ubuntu): swap, earlyoom, botni systemd xizmati qilish.
#
#   sudo bash deploy/sozlash.sh           # sozlaydi, botni ishga tushirmaydi (screen'dagi bot ishlayveradi)
#   sudo bash deploy/sozlash.sh --start   # screen'dagi botni to'xtatib, xizmat sifatida ishga tushiradi
#
# Qayta ishga tushirish xavfsiz: har qadam avval tekshiradi, bor narsani buzmaydi.
# Sozlamalar: SWAP_MB=1024 (swap hajmi), PYTHON=/yo'l/python (venv topilmasa), RUN_USER=foydalanuvchi.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Root huquqi kerak: sudo bash deploy/sozlash.sh"; exit 1
fi

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_USER="${RUN_USER:-${SUDO_USER:-$(stat -c %U "$DIR")}}"
SWAP_MB="${SWAP_MB:-1024}"
PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  for candidate in "$DIR/venv/bin/python" "$DIR/.venv/bin/python" "$(command -v python3 || true)"; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then PYTHON="$candidate"; break; fi
  done
fi
if [ -z "$PYTHON" ]; then echo "Python topilmadi. PYTHON=/yo'l/python bilan qayta ishga tushiring."; exit 1; fi

echo "Loyiha:   $DIR"
echo "Python:   $PYTHON"
echo "Foydalanuvchi: $RUN_USER"
echo

echo "== 1/3  Swap (qisqa xotira sakrashlarini yutadi)"
if swapon --show --noheadings | grep -q .; then
  swapon --show
else
  fallocate -l "${SWAP_MB}M" /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count="$SWAP_MB" status=none
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "swap yaratildi: ${SWAP_MB} MB"
fi
# Swap faqat zarurda ishlatilsin (aks holda disk "titraydi" — grafikdagi 1 GB/s).
cat > /etc/sysctl.d/99-edufayl.conf <<'EOF'
vm.swappiness=10
vm.vfs_cache_pressure=50
EOF
sysctl -q --system

echo
echo "== 2/3  earlyoom (server qotishidan oldin brauzer/node'ni o'chiradi, botni emas)"
if ! command -v earlyoom >/dev/null 2>&1; then
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq earlyoom
fi
install -m 644 "$DIR/deploy/earlyoom.default" /etc/default/earlyoom
systemctl enable -q earlyoom
systemctl restart earlyoom
systemctl --no-pager --lines=0 status earlyoom 2>/dev/null | head -3 || true

echo
echo "== 3/3  systemd xizmati: edufayl-bot (o'chsa 5 soniyada o'zi qaytadi)"
sed -e "s#__USER__#${RUN_USER}#g" -e "s#__DIR__#${DIR}#g" -e "s#__PYTHON__#${PYTHON}#g" \
    "$DIR/deploy/edufayl-bot.service" > /etc/systemd/system/edufayl-bot.service
systemctl daemon-reload
systemctl enable -q edufayl-bot

# Shu loyihaning boti (boshqa loyihalardagi main.py ga tegilmaydi): jarayon papkasi — $DIR.
RUNNING=""
for pid in $(pgrep -f "python[0-9.]* .*main\.py" || true); do
  if [ "$(readlink -f "/proc/$pid/cwd" 2>/dev/null)" = "$DIR" ]; then RUNNING="$RUNNING $pid"; fi
done
SERVICE_PID="$(systemctl show -p MainPID --value edufayl-bot 2>/dev/null || echo 0)"
if [ "${1:-}" = "--start" ]; then
  for pid in $RUNNING; do
    if [ "$pid" != "$SERVICE_PID" ]; then
      echo "Eski bot jarayoni to'xtatilmoqda (PID $pid)..."
      kill -TERM "$pid" 2>/dev/null || true
    fi
  done
  for _ in $(seq 1 30); do
    left=""
    for pid in $RUNNING; do
      if [ "$pid" != "$SERVICE_PID" ] && kill -0 "$pid" 2>/dev/null; then left="yes"; fi
    done
    [ -z "$left" ] && break
    sleep 1
  done
  systemctl restart edufayl-bot
  sleep 3
  systemctl --no-pager status edufayl-bot 2>/dev/null | head -5 || true
  echo
  echo "Tayyor. Jurnal: journalctl -u edufayl-bot -f"
else
  echo
  if [ -n "$RUNNING" ]; then
    echo "Bot hozir boshqa joyda (screen) ishlayapti: PID $(echo $RUNNING)."
    echo "Mijozlar ishi tugaganini admin paneldan tekshiring, keyin:"
    echo "    sudo bash deploy/sozlash.sh --start"
  else
    echo "Botni ishga tushirish:  sudo systemctl start edufayl-bot"
  fi
fi
