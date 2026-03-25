import axios from 'axios'

// Создаем экземпляр Axios с относительным базовым URL.
// В Docker запросы идут через nginx (порт 80), который проксирует /api/ на бэкенд.
// В локальной разработке Vite proxy перенаправляет /api/ на localhost:8000.
const api = axios.create({
    baseURL: '/api/v1',
    headers: {
        'Content-Type': 'application/json',
    },
});

// Интерцептор: автоматически добавляет токен авторизации в каждый запрос
api.interceptors.request.use((config) => {
    const token = localStorage.getItem('token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
}, (error) => {
    return Promise.reject(error);
});

// Interceptor ОТВЕТА (обрабатывает ошибки)
api.interceptors.response.use(
  (response) => response,
  (error) => {
    // Если сервер вернул 401 (Unauthorized)
    if (error.response && error.response.status === 401) {
      // Удаляем токен
      localStorage.removeItem('token');
      // Перенаправляем на логин
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// --- Auth API ---
export const signup = (email, password) => api.post('/auth/signup', { email, password });
export const login = async (email, password) => {
    // FastAPI ожидает form-data для логина (OAuth2PasswordRequestForm)
    const formData = new FormData();
    formData.append('username', email); // FastAPI ожидает поле 'username'
    formData.append('password', password);

    const response = await api.post('auth/login', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
};

// --- Agent API ---
export const askAgent = (question) => api.post('/analyze', { question })

// --- CSV Upload API ---
// Загружает CSV-файл на сервер через multipart/form-data.
// Возвращает промис с данными: { table_name, columns, row_count, message }
// axios сам выставит Content-Type: multipart/form-data с правильным boundary.
export const uploadCsv = (file) => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post('/upload-csv', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
    })
}

// Стриминг прогресса агента через Server-Sent Events.
// Используем fetch вместо EventSource, потому что EventSource не поддерживает
// пользовательские заголовки — а нам нужен Authorization: Bearer <token>.
//
// onEvent вызывается для каждого полученного события, например:
//   { type: 'thinking' }
//   { type: 'tool_call', tool: 'execute_sql_query' }
//   { type: 'done', answer: '...' }
export const askAgentStream = (question, onEvent) => {
    const token = localStorage.getItem('token')

    return fetch(
        `/api/v1/analyze/stream?question=${encodeURIComponent(question)}`,
        { headers: { Authorization: `Bearer ${token}` } }
    ).then(res => {
        // Обрабатываем HTTP-ошибки до начала чтения потока.
        // Без этой проверки при 401 код пытается читать тело ошибки как SSE-поток —
        // строк "data:" в нём нет, onEvent("done") никогда не вызывается → бесконечная загрузка.
        if (res.status === 401) {
            // Токен истёк или невалиден — сбрасываем сессию и редиректим на логин
            localStorage.removeItem('token')
            window.location.href = '/login'
            return
        }
        if (!res.ok) {
            // Любая другая серверная ошибка — пробрасываем исключение,
            // чтобы catch в Dashboard показал "Ошибка соединения с сервером."
            throw new Error(`Ошибка сервера: ${res.status}`)
        }

        const reader = res.body.getReader()
        const decoder = new TextDecoder()

        // Рекурсивно читаем поток чанк за чанком
        const pump = () => reader.read().then(({ done, value }) => {
            if (done) return

            // Декодируем байты в строку и разбиваем по строкам SSE-формата
            // Каждое событие имеет вид: "data: {...}\n\n"
            const text = decoder.decode(value)
            text.split('\n').forEach(line => {
                if (line.startsWith('data: ')) {
                    try {
                        onEvent(JSON.parse(line.slice(6)))
                    } catch {
                        // Игнорируем невалидный JSON (например, пустые keep-alive строки)
                    }
                }
            })

            return pump()
        })

        return pump()
    })
}