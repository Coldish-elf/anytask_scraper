# Anytask Scraper

[English](README.md)

`anytask-scraper` - Python-инструментарий для работы с [anytask.org](https://anytask.org/). В репозитории есть:

- CLI для экспорта и просмотра данных курса
- TUI для интерактивной навигации
- опциональный HTTP API для локальной автоматизации
- типизированная Python-библиотека для скриптов и интеграций

Во всех примерах используются только условные course ID и синтетические учётные данные.

## Что внутри

- `src/` layout с библиотекой и консольными entry point
- экспорт в JSON, CSV и Markdown
- сценарии для очереди проверок и ведомости
- опциональный FastAPI-сервер для локального HTTP-доступа
- тесты, линтер, type-checking и CI

## Требования

- Python `3.10+`

## Установка

Установка из текущей ветки:

```bash
pip install "git+https://github.com/Coldish-elf/anytask_scraper.git"
```

С поддержкой API:

```bash
pip install "anytask-scraper[api] @ git+https://github.com/Coldish-elf/anytask_scraper.git"
```

Для локальной разработки:

```bash
git clone https://github.com/Coldish-elf/anytask_scraper.git
cd anytask_scraper
pip install -e ".[dev,api]"
```

## Быстрый старт

Инициализируйте локальные настройки и шаблон учётных данных:

```bash
anytask-scraper settings init
```

Проверьте CLI:

```bash
anytask-scraper -h
```

Получите краткую сводку по условному курсу:

```bash
anytask-scraper course -c 12345 --show
```

Получите очередь проверок:

```bash
anytask-scraper queue -c 12345 --show
```

Запустите TUI:

```bash
anytask-tui
```

Запустите HTTP API:

```bash
anytask-api
```

## Документация

English:

- [Quick Start](docs-en/QuickStart.md)
- [CLI](docs-en/CLI.md)
- [TUI](docs-en/TUI.md)
- [HTTP API](docs-en/API.md)
- [Configuration](docs-en/Configuration.md)
- [Export Formats](docs-en/Export_Formats.md)
- [Architecture](docs-en/Architecture.md)
- [Library Reference](docs-en/Library_Reference.md)

Русский:

- [Быстрый старт](docs-ru/QuickStart.md)
- [CLI](docs-ru/CLI.md)
- [TUI](docs-ru/TUI.md)
- [HTTP API](docs-ru/API.md)
- [Конфигурация](docs-ru/Configuration.md)
- [Форматы экспорта](docs-ru/Export_Formats.md)
- [Архитектура](docs-ru/Architecture.md)
- [Справочник библиотеки](docs-ru/Library_Reference.md)

Файлы репозитория:

- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## Разработка

Локальные проверки:

```bash
pytest -q
ruff check src tests
ruff format --check src tests
mypy src
```

Сборка пакета:

```bash
python -m build
```
