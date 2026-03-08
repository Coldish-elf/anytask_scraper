# Быстрый старт

## 1. Установка

```bash
pip install git+https://github.com/Coldish-elf/anytask_scraper.git
```

Для разработки:

```bash
git clone https://github.com/Coldish-elf/anytask_scraper.git
cd anytask_scraper
pip install -e ".[dev]"
```

Проверка:

```bash
anytask-scraper -h
```

## 2. Инициализация настроек

```bash
anytask-scraper settings init
```

Эта команда создаёт:

- `.anytask_scraper_settings.json` - файл параметров по умолчанию
- `credentials.json` - шаблон логина и пароля, если файла ещё не было

## 3. Заполнение учётных данных

Заполните `credentials.json`:

```json
{
  "username": "your_login",
  "password": "your_password"
}
```

Поддерживаются и другие форматы файла (`key=value`, `key:value`, две строки `username`/`password`), подробнее см. в [Configuration](Configuration.md).

## 4. Первый экспорт курса

```bash
anytask-scraper course -c 12345 -f json -o ./output --show
```

Что произойдёт:

- выполнится вход на Anytask
- будет загружена страница курса `12345`
- данные сохранятся в `./output/course_12345.json`
- таблица будет показана в терминале.

## 5. Очередь преподавателя

```bash
anytask-scraper queue -c 12345 --deep -f markdown -o ./output
```

`--deep` дополнительно загружает страницы решений (issue) и комментарии.

## 6. Ведомость

```bash
anytask-scraper gradebook -c 12345 -f csv -o ./output
```

## 7. Автообнаружение курсов

```bash
anytask-scraper discover
```

## 8. Запуск TUI

```bash
anytask-tui
# или
anytask-scraper tui
```

Дальше используйте руководство [TUI](TUI.md).
