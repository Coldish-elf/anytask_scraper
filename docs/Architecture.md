# Архитектура проекта

## Назначение

Проект собирает данные из `anytask.org` и предоставляет три интерфейса:

1. CLI (`anytask-scraper`)
2. TUI (`anytask-tui`)
3. Python API (`import anytask_scraper`)

## Слои

### 1. Транспорт (`client.py`)

`AnytaskClient` отвечает за HTTP:

- login по форме Django с CSRF
- хранение cookies
- повторную авторизацию при истёкшей сессии
- загрузку HTML-страниц и AJAX JSON
- скачивание файлов и Colab notebook.

### 2. Парсинг (`parser.py`)

Преобразует HTML в типизированные модели (`dataclass`).

Ключевые входы:

- страница курса
- страница очереди
- страница issue
- страница ведомости
- страница профиля.

### 3. Модели (`models.py`)

Определяет структуру данных приложения:

- курс/задача
- очередь/комментарии/вложения
- ведомость по группам
- функции фильтрации (`filter_gradebook`, диапазон фамилий).

### 4. Сохранение (`storage.py`)

Экспортирует модели в `JSON` / `CSV` / `Markdown` и скачивает файлы submissions.

### 5. Отображение (`display.py`)

Рендерит Rich-таблицы и панели в терминале для CLI.

### 6. Оркестратор CLI (`cli.py`)

Связывает все уровни:

- разбирает аргументы
- применяет настройки
- выполняет авторизацию
- запускает сценарии `discover/course/queue/gradebook`
- пишет экспорт и/или печатает таблицы.

### 7. TUI (`tui/*`)

`Textual`-приложение для интерактивной работы:

- экран логина
- главный экран с вкладками
- экран submission
- контекстное action-меню
- фильтры, preview экспорта, copy-to-clipboard.

## Поток данных

Типовой поток:

1. `client` загружает HTML/JSON.
2. `parser` превращает вход в `dataclass`-объекты.
3. `models` применяют фильтры/нормализацию.
4. `storage` сохраняет результат на диск.
5. `display`/TUI показывают данные пользователю.

## Точки входа

- CLI entrypoint: `anytask_scraper.cli:main`
- TUI entrypoint: `anytask_scraper.tui:run`
- Библиотека: `anytask_scraper/__init__.py` (экспорт публичного API)

## Файлы состояния

- `.anytask_scraper_settings.json` - настройки CLI/TUI.
- `credentials.json` - логин/пароль.
- `.anytask_session.json` - cookie-сессия.
- `~/.config/anytask-scraper/courses.json` - сохранённый список курсов в TUI.
