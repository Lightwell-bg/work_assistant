#!/bin/sh
# Раннер вместо xvfb-run: на боевом VPS (2026-09-08) xvfb-run зависал
# насмерть в собственной проверке готовности дисплея (через xdpyinfo) ещё
# до запуска python — не помогало ни добавление xauth, ни x11-utils.
# Здесь всё под прямым контролем: поднимаем Xvfb сами, ждём фиксированную
# паузу вместо polling-проверки и запускаем приложение.
set -e

Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp &
export DISPLAY=:99

sleep 2

exec python -m upwork_assistant
