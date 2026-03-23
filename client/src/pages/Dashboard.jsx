import { useState, useRef, useEffect } from 'react';
import { askAgentStream } from '../api';

function Dashboard() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  // Текст текущего шага агента, отображается во время загрузки вместо точек
  const [statusText, setStatusText] = useState('');
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // --- Функция для обработки контента (Текст + Картинки) ---
  const renderContent = (content) => {
    // Регулярное выражение для поиска ссылок на картинки, которые генерирует агент
    const urlPattern = /(http:\/\/localhost:8000\/static\/plots\/[^\s]+\.png)/g;
    
    // Разбиваем текст на части: текст -> ссылка -> текст
    const parts = content.split(urlPattern);
    
    return parts.map((part, index) => {
      // Если часть совпадает с URL картинки
      if (part.match(urlPattern)) {
        return (
          <img 
            key={index} 
            src={part} 
            alt="Analysis Plot" 
            className="max-w-full h-auto rounded-lg shadow-md mt-2 border" 
          />
        );
      }
      // Иначе это просто текст
      return <span key={index} className="whitespace-pre-wrap">{part}</span>;
    });
  };

  // Подписи для каждого типа шага агента
  const STATUS_LABELS = {
    thinking:             '🤔 Агент анализирует вопрос...',
    execute_sql_query:    '🔍 Выполняю SQL запрос...',
    execute_python_code:  '🐍 Генерирую график...',
    tool_result:          '✅ Обрабатываю результаты...',
  };

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage = { role: 'user', content: input };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);
    setStatusText(STATUS_LABELS.thinking);

    try {
      await askAgentStream(input, (event) => {
        if (event.type === 'thinking') {
          setStatusText(STATUS_LABELS.thinking);
        } else if (event.type === 'tool_call') {
          // Показываем конкретный инструмент или универсальную подпись
          setStatusText(STATUS_LABELS[event.tool] ?? `🔧 Вызов ${event.tool}...`);
        } else if (event.type === 'tool_result') {
          setStatusText(STATUS_LABELS.tool_result);
        } else if (event.type === 'done') {
          // Получили финальный ответ — добавляем в историю и снимаем загрузку
          setMessages(prev => [...prev, { role: 'agent', content: event.answer }]);
          setIsLoading(false);
          setStatusText('');
        } else if (event.type === 'error') {
          setMessages(prev => [...prev, { role: 'agent', content: `Ошибка: ${event.message}` }]);
          setIsLoading(false);
          setStatusText('');
        }
      });
    } catch (err) {
      setMessages(prev => [...prev, { role: 'agent', content: 'Ошибка соединения с сервером.' }]);
      setIsLoading(false);
      setStatusText('');
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] max-w-4xl mx-auto bg-white shadow-xl">
      
      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-gray-50">
        {messages.length === 0 && !isLoading && (
          <div className="h-full flex flex-col items-center justify-center text-gray-400">
            <svg className="w-16 h-16 mb-4 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"></path>
            </svg>
            <p className="text-lg font-medium">Начните диалог</p>
            <p className="text-sm">Например: "Какие 5 клиентов принесли больше всего прибыли?"</p>
            <p className="text-sm mt-2">Или: "Нарисуй график распределения прибыли"</p>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-xl px-5 py-3 rounded-2xl shadow-sm ${
              msg.role === 'user' 
                ? 'bg-emerald-600 text-white rounded-br-none' 
                : 'bg-white text-gray-800 border border-gray-100 rounded-bl-none'
            }`}>
              {/* Используем функцию рендеринга здесь */}
              <div>{renderContent(msg.content)}</div>
            </div>
          </div>
        ))}

        {/* Индикатор загрузки: показывает текущий шаг агента вместо безликих точек */}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-white border border-gray-100 text-gray-500 px-5 py-3 rounded-2xl rounded-bl-none shadow-sm flex items-center space-x-2">
              {/* Анимированный спиннер */}
              <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
              <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
              <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
              {/* Текст текущего шага, обновляется по мере работы агента */}
              {statusText && <span className="text-sm ml-1">{statusText}</span>}
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="bg-white border-t border-gray-200 p-4 sticky bottom-0">
        <div className="flex items-end space-x-3 bg-gray-100 rounded-xl p-2 border border-gray-200 focus-within:border-emerald-500 focus-within:ring-1 focus-within:ring-emerald-500 transition-colors">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="Напишите запрос..."
            rows={1}
            className="flex-1 bg-transparent resize-none outline-none text-gray-800 placeholder-gray-500 text-sm p-2 max-h-32"
            disabled={isLoading}
          />
          <button 
            onClick={handleSend} 
            disabled={isLoading || !input.trim()}
            className="p-2 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center"
          >
            <svg className="w-5 h-5 rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"></path>
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;