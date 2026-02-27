# Форматы экспорта

Экспорт поддерживается для задач курса, очереди проверки, details решений (`submissions`) и ведомости.

## Общие правила

1. Базовая папка вывода берётся из `--output`, либо из `default_output`, либо `.`.
2. `--filename` позволяет задать имя выходного файла если расширение не указано, добавляется расширение текущего формата.
3. В `table` файл не создаётся: данные только печатаются в терминал.
4. Для `--include-columns` и `--exclude-columns` имена колонок чувствительны к точному написанию.

## JSON

Сохраняет структурированные данные, близкие к внутренним `dataclass`-моделям.

Имена файлов по умолчанию:

- `course_{course_id}.json`
- `queue_{course_id}.json`
- `gradebook_{course_id}.json`
- `submissions_{course_id}.json`

Если задан список колонок, JSON содержит только выбранные поля.

## CSV

Табличный экспорт для spreadsheet-инструментов.

Имена файлов по умолчанию:

- `course_{course_id}.csv`
- `queue_{course_id}.csv`
- `gradebook_{course_id}.csv`
- `submissions_{course_id}.csv`

Наборы колонок:

- `course` (student-view): `#`, `Title`, `Score`, `Status`, `Deadline`
- `course` (teacher-view): `#`, `Title`, `Section`, `Max Score`, `Deadline`
- `queue`: `#`, `Student`, `Task`, `Status`, `Reviewer`, `Updated`, `Grade`
- `submissions`: `Issue ID`, `Task`, `Student`, `Reviewer`, `Status`, `Grade`, `Max Score`, `Deadline`, `Comments`
- `gradebook`: `Group`, `Student`, динамические task-колонки, `Total`

## Markdown

Человеко-читаемый отчёт в `*.md`.

Имена файлов по умолчанию:

- `course_{course_id}.md`
- `queue_{course_id}.md`
- `gradebook_{course_id}.md`
- `submissions_{course_id}.md`

Особенности:

- `course` в полном режиме добавляет очищенные тексты описаний задач
- `queue` при наличии `submissions` добавляет секцию с issue и комментариями
- `gradebook` формируется по группам.

## Загрузка файлов решений

Это не отдельный формат, а дополнительный шаг для `queue`/`submissions`.

В CLI включается через `queue --download-files` (автоматически активирует `--deep`).

Что скачивается:

- вложения из комментариев
- Colab-ссылки (`colab.research.google.com`) как `*.ipynb`
- при неуспехе Colab создаётся `colab_{issue_id}.url.txt` с исходной ссылкой.

Структура: `<output>/<student_or_issue>/...`.
