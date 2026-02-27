# Anytask Scraper

**Anytask Scraper** - инструмент для сбора данных с [anytask.org](https://anytask.org/).

Проект представляет **CLI** и **TUI**. Также может использоваться как **Python-библиотека**.

## Возможности

- **TUI**: Интерактивный интерфейс для просмотра задач, очереди и оценок.
- **Студентам**: Просмотр дедлайнов, оценок и статусов задач.
- **Преподавателям**: Работа с очередью проверки, скачивание решений (включая Colab), экспорт ведомости.
- **Экспорт**: Поддержка JSON, CSV, Markdown.
- **Авторизация**: Поддержка логина/пароля и сессий (cookies).

## Установка

Требуется **Python 3.10+**.

```bash
git clone https://github.com/Coldish-elf/anytask_scraper
cd anytask_scraper
pip install -e .
```

## Быстрый старт

### Проверка

После установки убедитесь, что все работает корректно, вызвав:

```bash
anytask-scraper --help
```

Или запустите TUI:

```bash
anytask-tui
```

### CLI (Командная строка)

1. **Инициализация настроек** (рекомендуется):

    ```bash
    anytask-scraper settings init
    ```

    Это создаст файл настроек и шаблон для логина/пароля.

2. **Заполните логин и пароль**

3. **Получение задач курса**:

    ```bash
    anytask-scraper course -c 12345 --show
    ```

4. **Просмотр очереди на проверку**:

    ```bash
    anytask-scraper queue -c 12345 --show
    ```

## Документация

- **[QuickStart](docs/QuickStart.md)** - Быстрый старт.
- **[CLI](docs/CLI.md)** - Справочник команд.
- **[TUI](docs/TUI.md)** - Управление интерфейсом.
- **[Configuration](docs/Configuration.md)** - Настройки и авторизация.
- **[Export formats](docs/Export_formats.md)** - Форматы экспорта.
- **[Library Reference](docs/Library_Reference.md)** - Использование в Python-скриптах.
- **[Roadmap](docs/roadmap.md)** - План разработки.
- **[Changelog](docs/CHANGELOG.md)** - История изменений.
