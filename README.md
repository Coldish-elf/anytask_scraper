# Anytask Scraper

anytask-scraper - CLI, TUI и Python-библиотека для [anytask.org](https://anytask.org/).

## Требования

Нужен Python `3.10+`.

## Установка

```bash
git clone https://github.com/Coldish-elf/anytask_scraper
cd anytask_scraper
pip install -e .
```

## Быстрая проверка

```bash
anytask-scraper -h
# или быстрый старт TUI
anytask-tui
```

## Базовый сценарий CLI

1. Инициализируйте настройки:

```bash
anytask-scraper settings init
```

2. Заполните `credentials.json` (логин/пароль).

3. Получите данные по курсу:

```bash
anytask-scraper course -c 12345 --show
```

4. Получите очередь:

```bash
anytask-scraper queue -c 12345 --show
```

## Документация

- [Быстрый старт](docs/QuickStart.md)
- [CLI](docs/CLI.md)
- [TUI](docs/TUI.md)
- [Конфигурация](docs/Configuration.md)
- [Форматы экспорта](docs/Export_Formats.md)
- [Архитектура](docs/Architecture.md)
- [Справочник библиотеки](docs/Library_Reference.md)
- [Roadmap](docs/roadmap.md)
- [Changelog](docs/CHANGELOG.md)
