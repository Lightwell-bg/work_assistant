# Деплой на VPS через GitHub

Пошаговая инструкция: код лежит на GitHub, VPS тянет его через `git pull` и поднимает через Docker Compose. Это ручной процесс (без CI/CD) — соответствует тому, как сейчас устроен проект.

## Важный нюанс: разовый вход в Upwork — только с реальным экраном

Обычные циклы опроса на сервере работают в headful-режиме под Xvfb (виртуальный дисплей, без монитора) — `Dockerfile` это уже умеет, человек не нужен.

Но **самый первый вход** (`tools.login`) требует, чтобы человек увидел окно браузера и, возможно, ввёл код подтверждения устройства — Xvfb для этого не подходит (в нём никто не видит картинку). Поэтому:

**Вход выполняется один раз локально** (на вашей машине, как уже было сделано в этом проекте), а готовый профиль браузера **переносится на сервер** файлами — сервер сам никогда не логинится.

## 0. Код на GitHub

Репозиторий уже создан и код запушен: **https://github.com/Lightwell-bg/work_assistant**. Перед деплоем убедитесь, что актуальные изменения тоже там:

```bash
cd /d/1PythonProjects/20260905kwork_assist-main/work_assistant
git status   # проверьте, что .env и data/ не отслеживаются — .gitignore должен их исключать
git add .
git commit -m "..."
git push
```

Для приватного репозитория на сервере понадобится SSH-ключ или Personal Access Token — см. шаг 2.

## 1. Локально: один раз войти в Upwork (если ещё не делали)

```bash
source .venv/Scripts/activate
python -m upwork_assistant.tools.login
```

Откроется окно Chrome — войдите сами, при необходимости введите код подтверждения. После успеха профиль сохранится в `data/browser_profile/`.

## 2. Подготовка VPS

Всё ниже — от обычного (не root) пользователя. `sudo` нужен только там, где без него нельзя: поставить сам Docker и добавить пользователя в группу `docker`. После этого все остальные команды (`git`, `docker compose`, ...) выполняются без `sudo`.

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker           # применить новую группу в текущей сессии, без перелогина
docker compose version  # должен быть плагин Compose v2; проверка без sudo — значит группа применилась
```

`/opt` обычно принадлежит root — создайте папку через `sudo` один раз и сразу отдайте её себе, дальше `git`/`docker compose` внутри нее работают без `sudo`:

```bash
sudo mkdir -p /opt/work_assistant
sudo chown -R $USER:$USER /opt/work_assistant
cd /opt/work_assistant
git clone https://github.com/Lightwell-bg/work_assistant.git .
```

Если репозиторий публичный, команда выше отработает и сразу склонирует без вопросов. Если попросит `Username:`/`Password:` — значит приватный, и обычный пароль GitHub всё равно не примет (пароли по HTTPS отключены), нужен один из двух способов:

**Вариант А — Personal Access Token.** GitHub → Settings → Developer settings → Personal access tokens → Generate new token (classic), scope `repo`. Затем:

```bash
git clone https://<логин_github>:<токен>@github.com/Lightwell-bg/work_assistant.git .
```

(на запрос `Username:` — логин GitHub, на `Password:` — токен, не пароль от аккаунта).

**Вариант Б — SSH deploy key** (надёжнее — токен не остаётся в истории команд/URL):

```bash
ssh-keygen -t ed25519 -C "vps-work-assistant"   # Enter на все вопросы, без пароля на ключ
cat ~/.ssh/id_ed25519.pub
```

Скопируйте вывод в GitHub → репозиторий → Settings → Deploy keys → Add deploy key. После этого:

```bash
git clone git@github.com:Lightwell-bg/work_assistant.git .
```

## 3. Перенос секретов и профиля браузера на сервер

`.env`, `data/browser_profile/` и `data/profile.md` **не в git** (см. `.gitignore`) — переносятся отдельно, с локальной машины на сервер:

```bash
# с локальной машины (Git Bash / WSL)
scp .env user@server:/opt/work_assistant/.env
scp -r data/browser_profile user@server:/opt/work_assistant/data/
scp data/profile.md user@server:/opt/work_assistant/data/
```

На сервере проверьте, что все три на месте и `.env` заполнен реальными значениями (не плейсхолдерами из `.env.example`):

```bash
cd /opt/work_assistant
ls -la .env data/browser_profile data/profile.md
diff <(sed -E 's/=.*/=<V>/' .env) <(sed -E 's/=.*/=<V>/' .env.example)   # структура должна совпадать
```

## 4. Первый запуск

Собрать образ и накатить миграции на пустую БД сервера — один раз:

```bash
docker compose build
docker compose run --rm assistant alembic upgrade head
```

Поднять сервис:

```bash
docker compose up -d
docker compose logs -f --tail=100
```

Проверить, что всё поднялось:

```bash
curl -s http://127.0.0.1:8077/health
curl -s http://127.0.0.1:8077/stats
```

Если браузер не смог запуститься (ошибка про Chrome в логах) — см. «Траблшутинг» ниже.

## 5. Обновление после изменений в коде

```bash
cd /opt/work_assistant
git pull
docker compose up -d --build
# если менялась схема БД (появилась новая миграция в migrations/versions/):
docker compose run --rm assistant alembic upgrade head
curl -s http://127.0.0.1:8077/health
```

## Полезные команды

```bash
docker compose logs -f                          # логи в реальном времени
docker compose restart                           # перезапуск без пересборки
docker compose down                               # остановить (данные в ./data и ./logs сохранятся)
docker compose exec assistant alembic current    # текущая версия схемы БД
```

**Kill switch** — остановить/возобновить опрос без остановки контейнера:

```bash
curl -X POST http://127.0.0.1:8077/admin/pause
curl -X POST http://127.0.0.1:8077/admin/resume
curl -s http://127.0.0.1:8077/admin/status
```

**Бэкап** — БД и профиль браузера живут в `./data` на хосте (смонтировано томом), достаточно скопировать папку:

```bash
tar czf backup-$(date +%F).tar.gz data/
```

## Безопасность

- Не открывайте порт `8077` наружу публично напрямую — эндпоинты (включая `/admin/*`) без аутентификации. Либо держите его закрытым файрволом и ходите только по SSH-туннелю, либо поставьте reverse proxy (nginx/Caddy) с базовой аутентификацией перед приложением.
- `.env` никогда не коммитьте и не публикуйте — там пароль от Upwork, ключ OpenRouter и токен Telegram-бота.
- Приватный репозиторий на GitHub, если в коде когда-либо случайно окажется что-то чувствительное (сейчас `.gitignore` этого не допускает, но лишняя защита не помешает).

## Траблшутинг

**`xvfb-run: error: xauth command not found`, контейнер рестартует в цикле.** Реально словили это на боевом VPS — в образе не хватало пакета `xauth` (нужен `xvfb-run`, не только `xvfb`). Исправлено в `Dockerfile`; если у вас старый образ — подтяните код и пересоберите:
```bash
git pull && docker compose up -d --build
```

**Браузер не запускается в контейнере (ошибка про Chrome).** На реальном VPS `patchright install --with-deps chrome` в `Dockerfile` собрался без ошибок. Если у вас всё же не поставился браузер (проверить `docker compose exec assistant google-chrome --version`), раскомментируйте в `Dockerfile` блок с официальным репозиторием Google Chrome (`google-chrome-stable` через apt) — он там уже есть, закомментированный, с точными командами.

**Циклы опроса упираются в Cloudflare-челлендж.** Проверьте `UPWORK_HEADLESS=False` в `.env` — на реальной проверке headless-режим блокировался Cloudflare даже с валидной сессией. Headful в контейнере работает через Xvfb — `CMD` в `Dockerfile` уже это учитывает, ничего дополнительно настраивать не нужно.

**Сессия Upwork протухла (в логах `SessionInvalidError`).** Нужно повторить шаг 1 (вход локально) и шаг 3 (перенос обновлённого `data/browser_profile` на сервер) — заново, профиль не самообновляется без участия человека.

**Генерация отклика не работает / `data/profile.md` не найден.** Проверьте, что файл действительно скопирован на сервер (шаг 3) — без него скоринг работает, а генерация черновиков — нет.
