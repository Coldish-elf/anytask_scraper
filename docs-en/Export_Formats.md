# Export formats

Export is supported for course tasks, review queues, decision details (`submissions`) and statements.

## General rules

1. The base output folder is taken from `--output`, or from `default_output`, or `.`.
2. `--filename` allows you to specify the name of the output file; if the extension is not specified, the extension of the current format is added.
3. No file is created in `table`: the data is only printed to the terminal.
4. For `--include-columns` and `--exclude-columns`, column names are sensitive to exact spelling.

## JSON

Stores structured data similar to internal `dataclass` models.

Default file names:

- `course_{course_id}.json`
- `queue_{course_id}.json`
- `gradebook_{course_id}.json`
- `submissions_{course_id}.json`

If a list of columns is given, the JSON contains only the selected fields.

## CSV

Tabular export for spreadsheet tools.

Default file names:

- `course_{course_id}.csv`
- `queue_{course_id}.csv`
- `gradebook_{course_id}.csv`
- `submissions_{course_id}.csv`

Speaker sets:

- `course` (student-view): `#`, `Title`, `Score`, `Status`, `Deadline`
- `course` (teacher-view): `#`, `Title`, `Section`, `Max Score`, `Deadline`
- `queue`: `#`, `Student`, `Task`, `Status`, `Reviewer`, `Updated`, `Grade`
- `submissions`: `Issue ID`, `Task`, `Student`, `Reviewer`, `Status`, `Grade`, `Max Score`, `Deadline`, `Comments`
- `gradebook`: `Group`, `Student`, dynamic task columns, `Total`

## Markdown

Human-readable report in `*.md`.

Default file names:

- `course_{course_id}.md`
- `queue_{course_id}.md`
- `gradebook_{course_id}.md`
- `submissions_{course_id}.md`

Peculiarities:

- `course` in full mode adds cleared texts of task descriptions
- `queue` if `submissions` is present, adds a section with issue and comments
- `gradebook` is formed by groups.

## Loading solution files

This is not a separate format, but an additional step for `queue`/`submissions`.

Enabled in the CLI via `queue --download-files` (automatically enables `--deep`).

What is downloaded:

- attachments from comments
- Colab links (`colab.research.google.com`) as `last_first_task.ipynb`
- if Colab fails, `last_first_task.url.txt` is created with the original link.

Structure: `<output>/<student_or_issue>/...`.
