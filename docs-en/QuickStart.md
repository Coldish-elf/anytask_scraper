# Quick start

## 1. Installation

```bash
pip install git+https://github.com/Coldish-elf/anytask_scraper.git
```

For development:

```bash
git clone https://github.com/Coldish-elf/anytask_scraper.git
cd anytask_scraper
pip install -e ".[dev]"
```

Verify the installation:

```bash
anytask-scraper -h
```

## 2. Initializing settings

```bash
anytask-scraper settings init
```

This command creates:

- `.anytask_scraper_settings.json` - the default settings file
- `credentials.json` - a login/password template if the file does not exist yet

## 3. Filling in credentials

Fill out `credentials.json`:

```json
{
  "username": "your_login",
  "password": "your_password"
}
```

Other file formats are also supported (`key=value`, `key:value`, or two lines for `username` and `password`). See [Configuration](Configuration.md).

## 4. First export of the course

```bash
anytask-scraper course -c 12345 -f json -o ./output --show
```

What happens:

- the client logs in to Anytask
- course page `12345` is loaded
- data is saved to `./output/course_12345.json`
- the table is rendered in the terminal

## 5. Review queue

```bash
anytask-scraper queue -c 12345 --deep -f markdown -o ./output
```

`--deep` additionally loads issue pages and comments.

## 6. Gradebook

```bash
anytask-scraper gradebook -c 12345 -f csv -o ./output
```

## 7. Course discovery

```bash
anytask-scraper discover
```

## 8. Launch TUI

```bash
anytask-tui
anytask-scraper tui
```

Then continue with the [TUI](TUI.md) guide.
