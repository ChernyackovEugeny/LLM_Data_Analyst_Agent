import uvicorn

if __name__ == "__main__":
    # Запуск сервера
    uvicorn.run("app.app:app", host="0.0.0.0", port=8000, reload=True)