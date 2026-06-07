Grey Cardinal Tray Agent
========================

Трей-агент: на Windows одновременно пишет системный звук созвона и микрофон,
отправляет на сервер
(ASR → распознавание → задача появляется в Telegram-чате команды с кнопкой
«Создать карточку»).

ПРИВЯЗКА (один раз):
  1. На сайте https://fishingteam.su войдите → Профиль → «ПК-агент» →
     «Получить код привязки» → «Скопировать код».
  2. Запустите агент, в меню трея выберите «Привязать по коду».
  3. Вставьте код GC-XXXXXX. Готово: устройство появится на сайте как online.

ЗАПУСК:
  Windows : установите GreyCardinalAgent-x64.msi и запустите Grey Cardinal Agent
            из меню «Пуск». Агент добавляется в автозапуск, Python не нужен.
  macOS   : bash run_unix.sh        (нужен Python 3.10+)
  Linux   : sudo apt-get install -y gir1.2-ayatanaappindicator3-0.1 python3-gi
            bash run_unix.sh         (нужен Python 3.10+)

ИСПОЛЬЗОВАНИЕ:
  • Меню трея → «Записать сейчас (тест)» — записать ~25с и отправить.
  • Авто-запись включается, когда у команды идёт созвон (по /api/daemon/state).
  • Логи и config — пункты меню трея.
  • capture_mode = "mixed" пишет звук компьютера + микрофон.
    Также доступны "system_loopback" и "microphone".

Конфиг: <LOCALAPPDATA или ~>/GreyCardinal/Agent/tray_config.toml
