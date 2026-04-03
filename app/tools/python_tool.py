import ast
import logging
import os
import subprocess
import sys
import uuid

from langchain_core.tools import tool
from app.config import settings

logger = logging.getLogger(__name__)

PLOTS_DIR = "static/plots"
os.makedirs(PLOTS_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Docker sandbox: инициализация (один раз при старте модуля)
# ---------------------------------------------------------------------------
# Проверяем доступность Docker при импорте, а не per-request:
#   docker.ping() — TCP round-trip; делать его на каждый вызов инструмента
#   добавляло бы задержку без пользы. Результат не меняется во время работы.
#
# USE_SANDBOX=true устанавливается в docker-compose.yml (production).
# По умолчанию False → subprocess fallback для локальной разработки.
#
# Почему явная переменная USE_SANDBOX, а не автодетект Docker:
#   На dev-машине с Docker Desktop docker.ping() вернёт True, но именованного
#   volume plots_data не существует — sandbox провалится при монтировании volume.
#   Явный флаг разделяет "Docker доступен" и "инфраструктура настроена правильно".

_DOCKER_AVAILABLE = False
_docker_client = None

if settings.USE_SANDBOX:
    try:
        import docker as _docker_module
        _c = _docker_module.from_env()
        _c.ping()
        _docker_client = _c
        _DOCKER_AVAILABLE = True
        logger.info("Docker доступен — sandbox-режим АКТИВЕН (USE_SANDBOX=true)")
    except Exception as e:
        logger.error(
            f"USE_SANDBOX=true, но Docker недоступен: {e}. "
            "Проверьте монтирование /var/run/docker.sock в docker-compose.yml. "
            "Переключаюсь на subprocess fallback."
        )
else:
    logger.info("USE_SANDBOX=false — subprocess fallback (локальная разработка)")


# ---------------------------------------------------------------------------
# AST-валидация (Слой 1, работает в ОБОИХ путях: sandbox и fallback)
# ---------------------------------------------------------------------------
# Почему AST, а не regex/строковый поиск:
#   Regex "import os" ловит буквальный текст, но не:
#     from os import system   →  ast.ImportFrom(module='os')
#     import os as x          →  ast.Import(names=[alias(name='os', asname='x')])
#     __import__('os')        →  ast.Call(func=Name(id='__import__'))
#   AST парсит код в синтаксическое дерево — то же что Python-компилятор.
#   Все формы импорта дают узлы Import/ImportFrom с точным именем модуля.
#
# Почему AST запускается ПЕРЕД контейнером:
#   Запуск Docker-контейнера: 200-800ms. AST-парсинг: ~1ms.
#   Fast-fail экономит время и даёт понятное сообщение об ошибке,
#   которое LLM может исправить самостоятельно.

_BLOCKED_IMPORTS = frozenset({
    'os', 'sys', 'subprocess', 'socket',
    'requests', 'urllib', 'urllib3', 'http',
    'ftplib', 'smtplib', 'imaplib', 'poplib',
    'shutil', 'ctypes', 'importlib',
    'pickle', 'marshal', 'builtins',
})

# exec/eval/compile/__import__ обходят проверку импортов через runtime:
#   exec("import os; os.system('...')")  — AST видит только вызов exec()
#   __import__('os')                     — AST видит Call, не Import
_BLOCKED_CALLS = frozenset({'exec', 'eval', 'compile', '__import__'})


def _ast_validate(code: str) -> tuple[bool, str]:
    """
    Парсит код как AST и проверяет на запрещённые конструкции.
    Возвращает (is_valid, error_message).
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"Синтаксическая ошибка в коде: {e}"

    for node in ast.walk(tree):
        # Проверка: import X  и  import X as Y
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split('.')[0]
                if top in _BLOCKED_IMPORTS:
                    return False, f"Модуль '{alias.name}' запрещён по соображениям безопасности."

        # Проверка: from X import Y  (включая from os.path import join)
        if isinstance(node, ast.ImportFrom) and node.module:
            top = node.module.split('.')[0]
            if top in _BLOCKED_IMPORTS:
                return False, f"Импорт из '{node.module}' запрещён по соображениям безопасности."

        # Проверка вызовов: exec(), eval(), compile(), __import__()
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _BLOCKED_CALLS:
                return False, f"Вызов '{node.func.id}()' запрещён по соображениям безопасности."

    return True, ""


# ---------------------------------------------------------------------------
# Setup-код добавляется перед каждым пользовательским скриптом
# ---------------------------------------------------------------------------
# Предоставляет стандартные библиотеки для анализа данных без явного импорта.
# Это доверенный код приложения — AST-валидация применяется только к user-коду.

_SETUP_CODE = (
    "import pandas as pd\n"
    "import matplotlib\n"
    "matplotlib.use('Agg')\n"
    "import matplotlib.pyplot as plt\n"
    "import numpy as np\n"
    "import json\n"
)


# ---------------------------------------------------------------------------
# Путь 1: Docker sandbox (production, USE_SANDBOX=true)
# ---------------------------------------------------------------------------
# Docker-out-of-Docker (DooD) — проблема передачи файлов:
#   Backend работает в контейнере. Docker-демон на ХОСТЕ монтирует HOST-пути.
#   Нельзя: docker run -v /app/code.py:/workspace/code.py
#     — /app/code.py существует только внутри backend-контейнера.
#
# Решение: volume plots_data как общая шина данных:
#   Backend пишет _tmp_{uuid}.py в static/plots/ (= volume plots_data на хосте)
#   Sandbox монтирует тот же plots_data volume по имени
#   Sandbox читает и выполняет скрипт, пишет PNG графики туда же
#   Backend удаляет временный скрипт
#
# Ограничения sandbox-контейнера:
#   network_disabled=True  — нет TCP/UDP, нет exfiltration и reverse shell
#   mem_limit="512m"       — hard cap, OOM kill при превышении
#   nano_cpus=500_000_000  — максимум 0.5 CPU (1 CPU = 1_000_000_000)
#   env не передаётся     — пустое окружение, sandbox не видит секреты
#   remove=False           — удаляем вручную в finally для гарантии очистки
#
# detach=True + container.wait() вместо detach=False:
#   detach=False возвращает смешанный stdout+stderr как один bytes-объект.
#   Раздельный сбор позволяет отличить данные (stdout) от трейсбеков (stderr).

def _run_in_sandbox(code: str) -> str:
    import docker  # noqa: F811 — уже импортирован на уровне модуля если _DOCKER_AVAILABLE

    fname = f"_tmp_{uuid.uuid4().hex}.py"
    host_path = os.path.join(PLOTS_DIR, fname)
    sandbox_script_path = f"/workspace/static/plots/{fname}"

    with open(host_path, 'w', encoding='utf-8') as f:
        f.write(_SETUP_CODE + "\n" + code)

    container = None
    try:
        container = _docker_client.containers.run(
            image=settings.SANDBOX_IMAGE_NAME,
            command=["python", sandbox_script_path],
            volumes={
                settings.PLOTS_VOLUME_NAME: {
                    'bind': '/workspace/static/plots',
                    'mode': 'rw',
                }
            },
            mem_limit="512m",
            nano_cpus=500_000_000,
            network_disabled=True,
            user="root",
            detach=True,
            remove=False,
            # env= не передаём: Docker по умолчанию даёт пустое окружение.
            # Sandbox не получит DEEPSEEK_API_KEY, SECRET_KEY, DATABASE_URL.
        )

        try:
            result = container.wait(timeout=30)
            exit_code = result.get('StatusCode', -1)
        except Exception:
            try:
                container.kill()
            except Exception:
                pass
            return "Превышено время выполнения (30 сек)."

        stdout = container.logs(stdout=True, stderr=False).decode('utf-8', errors='replace').strip()
        stderr = container.logs(stdout=False, stderr=True).decode('utf-8', errors='replace').strip()

        if exit_code != 0:
            return f"Ошибка Python:\n{stderr}"
        return stdout or "Код выполнен успешно."

    except docker.errors.ImageNotFound:
        return (
            f"Образ sandbox не найден ({settings.SANDBOX_IMAGE_NAME}). "
            "Выполните: docker compose build sandbox"
        )
    except Exception as e:
        logger.exception("Неожиданная ошибка при запуске sandbox")
        return f"Ошибка sandbox: {str(e)}"

    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass
        if os.path.exists(host_path):
            try:
                os.remove(host_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Путь 2: subprocess fallback (локальная разработка, USE_SANDBOX=false)
# ---------------------------------------------------------------------------
# AST-валидация уже прошла к этому моменту.
# Чистое окружение: секреты из os.environ НЕ передаются в subprocess.
# Это важно: даже если LLM случайно напишет os.environ.get('KEY'),
# переменных в окружении subprocess не будет.
#
# finally гарантирует удаление temp-файла даже при TimeoutExpired
# (в оригинальном коде os.remove был до except — файл утекал при таймауте).

_SUBPROCESS_SAFE_ENV_KEYS = {
    'PATH', 'PYTHONPATH',
    'TEMP', 'TMP', 'TMPDIR',
    'HOME', 'USERPROFILE',
    'SYSTEMROOT', 'SYSTEMDRIVE',
    'LANG', 'LC_ALL', 'LC_CTYPE',
}


def _run_in_subprocess(code: str) -> str:
    import tempfile

    clean_env = {
        k: os.environ[k]
        for k in _SUBPROCESS_SAFE_ENV_KEYS
        if k in os.environ
    }
    clean_env['PYTHONIOENCODING'] = 'utf-8'

    script_path = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix='.py', delete=False, mode='w', encoding='utf-8'
        ) as f:
            script_path = f.name
            f.write(_SETUP_CODE + "\n" + code)

        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=30,
            env=clean_env,
        )

        if result.returncode != 0:
            return f"Ошибка Python:\n{result.stderr}"
        return result.stdout or "Код выполнен успешно."

    except subprocess.TimeoutExpired:
        return "Превышено время выполнения (30 сек)."
    except Exception as e:
        return f"Ошибка: {str(e)}"
    finally:
        if script_path and os.path.exists(script_path):
            try:
                os.remove(script_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Лимит размера кода
# ---------------------------------------------------------------------------
# Защищает от вставки больших массивов данных прямо в код.
# Нормальный скрипт с графиком: 500-2000 символов.
# Скрипт с 200 захардкоженными строками: 8000-15000 символов.
# Промпт-правило не работает — модель его игнорирует. Лимит в коде — жёсткий.
_MAX_CODE_SIZE = 4000


# ---------------------------------------------------------------------------
# Публичный инструмент агента
# ---------------------------------------------------------------------------

@tool
def execute_python_code(code: str) -> str:
    """
    Выполняет Python код для анализа данных или построения графиков.
    Доступны библиотеки: pandas (pd), matplotlib.pyplot (plt), numpy (np), json.

    Для загрузки результатов SQL-запроса используй путь из ToolMessage:
        df = pd.read_csv('путь_из_результата_sql')

    Для сохранения графиков используй:
        plt.savefig('static/plots/название.png')
        plt.close()
    Затем выведи путь: print('/static/plots/название.png')

    Args:
        code: Python код для выполнения.
    """

    # Слой 0: проверка размера кода.
    # Выполняется до AST-валидации — O(1), без парсинга.
    # Большой код = захардкоженные данные. Решение: агрегировать в SQL.
    if len(code) > _MAX_CODE_SIZE:
        return (
            f"Код отклонён: слишком большой ({len(code)} символов, максимум {_MAX_CODE_SIZE}). "
            "Не вставляй данные из SQL прямо в Python-код. "
            "Напиши новый SQL-запрос с агрегацией (GROUP BY месяц/квартал) "
            "чтобы получить не более 20-30 строк, и используй только эти значения в коде."
        )

    # Слой 1: AST-валидация — быстрый отказ, работает в обоих путях
    is_valid, error_msg = _ast_validate(code)
    if not is_valid:
        return f"Код отклонён политикой безопасности: {error_msg}"

    # Слой 2: изолированное выполнение (sandbox или subprocess)
    if _DOCKER_AVAILABLE:
        return _run_in_sandbox(code)
    else:
        return _run_in_subprocess(code)
