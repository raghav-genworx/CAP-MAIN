# Code Execution API

The code execution service runs submitted code through a self-hosted Judge0
engine. Configure the engine URL with `JUDGE0_BASE_URL`; for a local Judge0
deployment the default is `http://localhost:2358`.

## Execute Code

`POST /api/v1/executions`

```json
{
  "language": "python",
  "source_code": "a, b = map(int, input().split())\nprint(a + b)",
  "stdin": "2 3\n"
}
```

Use `language_id` instead of `language` when the caller already knows the exact
Judge0 language ID.

```json
{
  "language_id": 71,
  "source_code": "print(input().upper())",
  "stdin": "hello"
}
```

The response includes Judge0 status metadata, standard output, standard error,
compiler output, runtime, memory, and exit details.

## List Languages

`GET /api/v1/executions/languages`

Returns the languages supported by the configured Judge0 deployment.
