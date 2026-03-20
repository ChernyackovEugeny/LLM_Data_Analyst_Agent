import axios from 'axios'

// Создаем экземпляр Axios с базовым URL нашего бэкенда
const api = axios.create({
    baseURL: 'http://localhost:8000/api/v1',
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