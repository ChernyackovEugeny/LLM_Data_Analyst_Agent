import os
import sys
import subprocess
import tempfile
from langchain_core.tools import tool
from app.config import settings

# Папка для сохранения графиков (относительно рабочей директории uvicorn — корня проекта)
PLOTS_DIR = "static/plots"
os.makedirs(PLOTS_DIR, exist_ok=True)

@tool
def execute_python_code(code: str) -> str:
    """
    Выполняет Python код для анализа данных или построения графиков.
    Используйте библиотеки pandas (as pd) и matplotlib.pyplot (as plt).
    Данные из SQL запросов можно передать через переменную 'df' (JSON string) или создать внутри кода.
    
    Для сохранения графиков ОБЯЗАТЕЛЬНО используйте:
    plt.savefig('static/plots/plot_name.png')
    plt.close()
    
    Args:
        code: Python код для выполнения.
    """

    try:
        # Код-заглушка с импортами, который будет выполнен перед кодом агента.
        # Гарантирует, что pandas, matplotlib и другие библиотеки всегда доступны.
        setup_code = (
            "import pandas as pd\n"
            "import matplotlib.pyplot as plt\n"
            "import json\n"
            "import sys\n"
            "import matplotlib\n"
            "import matplotlib\n"
            # Используем backend без GUI — иначе matplotlib пытается открыть окно,
            # что не работает на сервере
            "matplotlib.use('Agg')\n"
        )

        full_code = setup_code + code

        # Создаём временный файл в системной папке temp (например, C:\Users\...\AppData\Local\Temp).
        # Это важно: файл НЕ попадает в папку проекта, поэтому uvicorn не замечает его
        # и не перезапускает сервер во время выполнения кода.
        with tempfile.NamedTemporaryFile(
            suffix=".py", delete=False, mode="w", encoding="utf-8"
        ) as f:
            script_path = f.name
            f.write(full_code)

        # Запускаем скрипт в отдельном процессе с тем же интерпретатором Python.
        # PYTHONIOENCODING=utf-8 — без этого Windows пытается кодировать stdout в cp1252
        # и падает с UnicodeEncodeError если в print() есть emoji или кириллица.
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=30,
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}
        )

        # Удаляем временный файл после выполнения
        if os.path.exists(script_path):
            os.remove(script_path)

        # Если процесс завершился с ошибкой — возвращаем stderr агенту,
        # чтобы он мог проанализировать и исправить код
        if result.returncode != 0:
            return f"Ошибка выполнения Python: {result.stderr}"

        return result.stdout if result.stdout else "Код выполнен успешно."

    except subprocess.TimeoutExpired:
        return "Превышено время выполнения (30 сек)."
    except Exception as e:
        return f"Ошибка: {str(e)}"