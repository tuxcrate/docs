# docs

The Tuxcrate website for ready-to-run open-source apps.

## Checks

With Python 3.13+ and Node.js 22 installed:

```sh
python -m pip install -r requirements-test.txt
ruff check --select ALL --ignore D203,D213,COM812,CPY001 .
python -m pytest macros/tests
node --test macros/tests/test_container_tags.cjs
```

Ruff enables all rules except conflicting docstring conventions (`D203`, `D213`),
formatter-incompatible trailing commas (`COM812`), and mandatory copyright headers
(`CPY001`). Intentional exceptions are documented beside the affected code.
