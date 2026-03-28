"""
Unit тесты для app/tools/python_tool.py

Покрываем только AST-валидацию (_ast_validate).
Subprocess и Docker-sandbox намеренно не тестируются здесь:
  - subprocess требует реальной Python-среды с нужными библиотеками
  - Docker-sandbox требует запущенного Docker daemon и образа

AST-валидация — самый критичный слой безопасности: она блокирует
опасные импорты и вызовы ещё до какого-либо выполнения кода.
"""
import pytest

from app.tools.python_tool import _ast_validate


class TestBlockedImports:
    """Модули из blocklist должны отклоняться."""

    def test_blocks_import_os(self):
        is_valid, msg = _ast_validate("import os")
        assert is_valid is False
        assert "os" in msg

    def test_blocks_import_sys(self):
        is_valid, msg = _ast_validate("import sys")
        assert is_valid is False
        assert "sys" in msg

    def test_blocks_import_subprocess(self):
        is_valid, msg = _ast_validate("import subprocess")
        assert is_valid is False

    def test_blocks_import_socket(self):
        is_valid, msg = _ast_validate("import socket")
        assert is_valid is False

    def test_blocks_import_requests(self):
        is_valid, msg = _ast_validate("import requests")
        assert is_valid is False

    def test_blocks_import_shutil(self):
        is_valid, msg = _ast_validate("import shutil")
        assert is_valid is False

    def test_blocks_import_pickle(self):
        is_valid, msg = _ast_validate("import pickle")
        assert is_valid is False

    def test_blocks_import_ctypes(self):
        is_valid, msg = _ast_validate("import ctypes")
        assert is_valid is False

    def test_blocks_import_with_alias(self):
        """import os as operating_system — тоже блокируется."""
        is_valid, msg = _ast_validate("import os as operating_system")
        assert is_valid is False

    def test_blocks_from_os_import_path(self):
        """from os import path — блокируется."""
        is_valid, msg = _ast_validate("from os import path")
        assert is_valid is False

    def test_blocks_from_subprocess_import_run(self):
        is_valid, msg = _ast_validate("from subprocess import run")
        assert is_valid is False

    def test_blocks_from_os_path_import_join(self):
        """from os.path import join — блокируется (top-level = 'os')."""
        is_valid, msg = _ast_validate("from os.path import join")
        assert is_valid is False

    def test_blocks_urllib(self):
        is_valid, msg = _ast_validate("import urllib")
        assert is_valid is False

    def test_blocks_http(self):
        is_valid, msg = _ast_validate("import http")
        assert is_valid is False

    def test_blocks_importlib(self):
        is_valid, msg = _ast_validate("import importlib")
        assert is_valid is False

    def test_blocks_builtins(self):
        is_valid, msg = _ast_validate("import builtins")
        assert is_valid is False


class TestBlockedCalls:
    """Опасные встроенные функции должны блокироваться."""

    def test_blocks_eval(self):
        is_valid, msg = _ast_validate("eval('print(1)')")
        assert is_valid is False
        assert "eval" in msg

    def test_blocks_exec(self):
        is_valid, msg = _ast_validate("exec('import os')")
        assert is_valid is False
        assert "exec" in msg

    def test_blocks_compile(self):
        is_valid, msg = _ast_validate("compile('import os', '', 'exec')")
        assert is_valid is False
        assert "compile" in msg

    def test_blocks_dunder_import(self):
        is_valid, msg = _ast_validate("__import__('os')")
        assert is_valid is False
        assert "__import__" in msg

    def test_blocks_eval_in_function(self):
        """eval внутри функции тоже блокируется."""
        code = "def run():\n    return eval('1+1')"
        is_valid, msg = _ast_validate(code)
        assert is_valid is False


class TestAllowedCode:
    """Безопасный код должен проходить валидацию."""

    def test_allows_import_pandas(self):
        is_valid, _ = _ast_validate("import pandas as pd")
        assert is_valid is True

    def test_allows_import_matplotlib(self):
        is_valid, _ = _ast_validate("import matplotlib.pyplot as plt")
        assert is_valid is True

    def test_allows_import_numpy(self):
        is_valid, _ = _ast_validate("import numpy as np")
        assert is_valid is True

    def test_allows_import_json(self):
        is_valid, _ = _ast_validate("import json")
        assert is_valid is True

    def test_allows_import_math(self):
        is_valid, _ = _ast_validate("import math")
        assert is_valid is True

    def test_allows_safe_arithmetic(self):
        code = "result = 2 + 2\nprint(result)"
        is_valid, _ = _ast_validate(code)
        assert is_valid is True

    def test_allows_dataframe_operations(self):
        code = (
            "import pandas as pd\n"
            "df = pd.DataFrame({'a': [1, 2], 'b': [3, 4]})\n"
            "print(df.describe())"
        )
        is_valid, _ = _ast_validate(code)
        assert is_valid is True

    def test_allows_matplotlib_plotting(self):
        code = (
            "import matplotlib.pyplot as plt\n"
            "plt.plot([1, 2, 3], [4, 5, 6])\n"
            "plt.savefig('static/plots/test.png')\n"
            "print('/static/plots/test.png')"
        )
        is_valid, _ = _ast_validate(code)
        assert is_valid is True

    def test_allows_list_comprehension(self):
        code = "result = [x**2 for x in range(10)]\nprint(result)"
        is_valid, _ = _ast_validate(code)
        assert is_valid is True

    def test_allows_function_definition(self):
        code = "def compute(x):\n    return x * 2\nprint(compute(5))"
        is_valid, _ = _ast_validate(code)
        assert is_valid is True


class TestSyntaxErrors:
    def test_returns_false_on_syntax_error(self):
        is_valid, msg = _ast_validate("def broken(:\n    pass")
        assert is_valid is False
        assert "синтаксическ" in msg.lower() or "syntax" in msg.lower()

    def test_returns_error_message_on_syntax_error(self):
        is_valid, msg = _ast_validate("x = (1 +")
        assert is_valid is False
        assert msg != ""
