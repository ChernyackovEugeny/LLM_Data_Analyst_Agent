import axios from 'axios'

// Создаем экземпляр Axios с относительным базовым URL.
// В Docker запросы идут через nginx (порт 80), который проксирует /api/ на бэкенд.
// В локальной разработке Vite proxy перенаправляет /api/ на localhost:8000.
const api = axios.create({
    baseURL: '/api/v1',
    headers: {
        'Content-Type': 'application/json',
    },
    // withCredentials=true: axios отправляет HttpOnly cookie в cross-origin запросах
    // (нужно для dev: Vite на 5173 → backend на 8000 через proxy).
    // В Docker всё same-origin — куки отправляются автоматически и без этого флага,
    // но явное указание не мешает.
    withCredentials: true,
});

// Interceptor ОТВЕТА: при 401 пробуем обновить access_token через refresh endpoint.
// Если refresh тоже не помог — редиректим на /login.
// _retry флаг на error.config предотвращает бесконечный цикл повторов.
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const isAuthEndpoint = error.config?.url?.includes('/auth/');
    if (error.response?.status === 401 && !isAuthEndpoint) {
      if (!error.config._retry) {
        error.config._retry = true;
        try {
          await api.post('/auth/refresh');
          return api(error.config);
        } catch {
          window.location.href = '/login';
        }
      } else {
        window.location.href = '/login';
      }
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

// Проверка состояния аутентификации — вызывается при загрузке приложения.
// 200 = токен валидный, 401 = не залогинен или токен истёк.
export const checkAuth = () => api.get('/auth/me');

// Logout: сервер удаляет оба HttpOnly cookie (access_token + refresh_token).
export const logout = () => api.post('/auth/logout');

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

// --- Chat API ---
export const createChat = () => api.post('/chats');
export const listChats = () => api.get('/chats');
export const deleteChat = (chatId) => api.delete(`/chats/${chatId}`);
export const getChatMessages = (chatId) => api.get(`/chats/${chatId}/messages`);

// Стриминг прогресса агента через Server-Sent Events.
// Используем fetch вместо EventSource, потому что EventSource не поддерживает
// пользовательские заголовки.
// Cookie отправляется браузером автоматически (same-origin / credentials: 'same-origin').
//
// onEvent вызывается для каждого полученного события, например:
//   { type: 'thinking' }
//   { type: 'tool_call', tool: 'execute_sql_query' }
//   { type: 'done', answer: '...' }
export const askAgentStream = async (chatId, question, onEvent) => {
    const url = `/api/v1/analyze/stream?chat_id=${chatId}&question=${encodeURIComponent(question)}`;

    const makeRequest = () => fetch(url, { credentials: 'same-origin' });

    let res = await makeRequest();

    // При 401 пробуем обновить токен и повторить запрос (SSE использует fetch, не axios)
    if (res.status === 401) {
        try {
            await api.post('/auth/refresh');
            res = await makeRequest();
        } catch {
            window.location.href = '/login';
            return;
        }
    }

    // Обрабатываем HTTP-ошибки до начала чтения потока.
    if (!res.ok) {
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
}
