#!/usr/bin/env bash
# Grey Cardinal Tray Agent — запуск на macOS / Linux.
# Кросс-платформенный (тот же агент, что и на Windows), запускается из исходника.
set -e
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
echo "Grey Cardinal Tray Agent (macOS/Linux)"

# venv (по желанию)
if [ ! -d .venv ]; then
  "$PY" -m venv .venv
fi
. .venv/bin/activate

pip install -q --upgrade pip
pip install -q -r requirements.txt

# Системный трей:
#   macOS  — нужен pyobjc (ставится ниже автоматически).
#   Linux  — нужен GTK + AppIndicator:
#            sudo apt-get install -y gir1.2-ayatanaappindicator3-0.1 python3-gi
case "$(uname -s)" in
  Darwin) pip install -q pyobjc-framework-Cocoa pyobjc-framework-Quartz ;;
esac

echo "Запуск… (иконка появится в трее / меню-баре)"
exec "$PY" tray_agent.py
