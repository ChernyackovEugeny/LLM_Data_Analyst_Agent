import uvicorn
from app.config import settings

if __name__ == "__main__":
    # reload=True только в DEBUG-режиме: в production (Docker) перезагрузка не нужна
    # и создаёт лишний overhead (watchdog thread на каждый файл проекта).
    uvicorn.run("app.app:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)