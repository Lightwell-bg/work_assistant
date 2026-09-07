# syntax=docker/dockerfile:1

FROM python:3.13-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

# ---------------------------------------------------------------- сборка
FROM base AS builder
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --prefix=/install .

# ---------------------------------------------------------------- рантайм
FROM base AS runtime
# Браузеры ставятся в общий каталог, а не в /root, иначе непривилегированный
# пользователь их не увидит.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/browsers

COPY --from=builder /install /usr/local

# ВАЖНО: устанавливаем канал "chrome" (настоящий Google Chrome), а не
# бандленный "chromium" — BrowserSession (adapters/upwork/browser.py)
# запускается с channel="chrome" сознательно, ради стелса Patchright.
# Установка "chromium" вместо "chrome" не даст ошибки на этом шаге, но
# приложение упадёт при первом же запуске браузера в рантайме.
#
# xvfb — на реальном прогоне 2026-09-07 выяснилось, что UPWORK_HEADLESS=True
# ловит челлендж Cloudflare даже с валидной сессией; headless=False
# (по умолчанию в .env.example) требует X-дисплея, которого в контейнере
# без монитора нет — поэтому CMD ниже оборачивает запуск в xvfb-run.
# На реальном VPS (Ubuntu) 2026-09 сборка образа с `patchright install
# --with-deps chrome` прошла без ошибок (контейнер потом падал на xauth,
# т.е. до Chrome дело ещё не дошло) — если на вашем сервере эта команда
# всё же не поставит браузер (проверить `google-chrome --version` внутри
# контейнера), раскомментируйте официальный репозиторий Google Chrome ниже
# вместо `patchright install --with-deps chrome`:
#
#   RUN curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
#    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
#    && apt-get update && apt-get install -y --no-install-recommends google-chrome-stable && rm -rf /var/lib/apt/lists/*
RUN apt-get update \
 && apt-get install -y --no-install-recommends xvfb xauth \
 && rm -rf /var/lib/apt/lists/* \
 && patchright install --with-deps chrome \
 && useradd --create-home --shell /usr/sbin/nologin app \
 && mkdir -p /app/data /app/logs \
 && chown -R app:app /app /opt/browsers

USER app

EXPOSE 8077

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import httpx,sys; sys.exit(0 if httpx.get('http://127.0.0.1:8077/health', timeout=5).status_code == 200 else 1)"

CMD ["xvfb-run", "--auto-servernum", "--server-args=-screen 0 1920x1080x24", "python", "-m", "upwork_assistant"]
