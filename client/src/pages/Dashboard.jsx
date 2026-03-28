import { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { askAgentStream, uploadCsv, createChat, listChats, deleteChat, getChatMessages } from '../api';

function Dashboard() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  // Текст текущего шага агента, отображается во время загрузки вместо точек
  const [statusText, setStatusText] = useState('');
  // Флаг загрузки CSV-файла
  const [isUploading, setIsUploading] = useState(false);
  // URL графика для полноэкранного просмотра (null = модал закрыт)
  const [zoomedImage, setZoomedImage] = useState(null);
  // Список чатов пользователя
  const [chats, setChats] = useState([]);
  // ID активного чата (null пока не загружен)
  const [activeChatId, setActiveChatId] = useState(null);
  // Флаг начальной загрузки чатов
  const [chatsLoading, setChatsLoading] = useState(true);
  const messagesEndRef = useRef(null);
  // Ref на скрытый <input type="file"> — кнопка-скрепка кликает по нему программно
  const fileInputRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Закрывает lightbox по нажатию Escape
  useEffect(() => {
    const handleKey = (e) => { if (e.key === 'Escape') setZoomedImage(null); };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, []);

  // При монтировании загружаем список чатов.
  // Если есть чаты — открываем первый (самый свежий).
  // Если нет — создаём новый автоматически.
  useEffect(() => {
    const init = async () => {
      try {
        const res = await listChats();
        const loaded = res.data;
        if (loaded.length > 0) {
          setChats(loaded);
          await openChat(loaded[0].id);
        } else {
          await handleNewChat();
        }
      } finally {
        setChatsLoading(false);
      }
    };
    init();
  }, []);

  // Загружает сообщения чата и делает его активным
  const openChat = async (chatId) => {
    setActiveChatId(chatId);
    try {
      const res = await getChatMessages(chatId);
      // MessageOut: { role, content, created_at } → { role, content }
      setMessages(res.data.map(m => ({ role: m.role, content: m.content })));
    } catch {
      setMessages([]);
    }
  };

  // Создаёт новый чат и открывает его
  const handleNewChat = async () => {
    try {
      const res = await createChat();
      const newChat = res.data;
      setChats(prev => [newChat, ...prev]);
      setActiveChatId(newChat.id);
      setMessages([]);
    } catch {
      // Тихо игнорируем — пользователь увидит что чат не появился
    }
  };

  // Переключение между чатами
  const handleSelectChat = async (chatId) => {
    if (chatId === activeChatId || isLoading) return;
    await openChat(chatId);
  };

  // Удаление чата
  const handleDeleteChat = async (e, chatId) => {
    e.stopPropagation(); // не переключаем на удаляемый чат
    try {
      await deleteChat(chatId);
      const remaining = chats.filter(c => c.id !== chatId);
      setChats(remaining);

      if (chatId === activeChatId) {
        // Удалили активный чат — переключаемся на следующий или создаём новый
        if (remaining.length > 0) {
          await openChat(remaining[0].id);
        } else {
          await handleNewChat();
        }
      }
    } catch {
      // Тихо игнорируем
    }
  };

  // Конвертирует голые URL графиков в markdown-синтаксис изображений,
  // чтобы ReactMarkdown рендерил их через кастомный компонент img
  const prepareContent = (content) => {
    // Оборачиваем только голые пути — те, что ещё не внутри ![...](...)
    // Негативный lookbehind (?<!\]\() не матчит пути уже внутри markdown-изображений
    return content.replace(/(?<!\]\()(\/static\/plots\/[^\s]+\.png)/g, '\n![график]($1)\n');
  };

  // Кастомные компоненты ReactMarkdown — задают стили для каждого markdown-элемента
  const markdownComponents = {
    h1: ({ children }) => <h1 className="text-lg font-bold mt-3 mb-2 text-gray-900">{children}</h1>,
    h2: ({ children }) => <h2 className="text-base font-bold mt-3 mb-1 text-gray-900">{children}</h2>,
    h3: ({ children }) => <h3 className="text-sm font-semibold mt-2 mb-1 text-gray-800">{children}</h3>,
    strong: ({ children }) => <strong className="font-semibold text-gray-900">{children}</strong>,
    ul: ({ children }) => <ul className="list-disc list-outside pl-4 my-1 space-y-0.5">{children}</ul>,
    ol: ({ children }) => <ol className="list-decimal list-outside pl-4 my-1 space-y-0.5">{children}</ol>,
    li: ({ children }) => <li className="text-sm leading-relaxed">{children}</li>,
    p: ({ children }) => <p className="my-1 leading-relaxed">{children}</p>,
    code: ({ children }) => (
      <code className="bg-gray-100 text-gray-800 px-1 py-0.5 rounded text-xs font-mono">{children}</code>
    ),
    table: ({ children }) => (
      <div className="overflow-x-auto my-2">
        <table className="border-collapse w-full text-sm">{children}</table>
      </div>
    ),
    thead: ({ children }) => <thead className="bg-gray-100">{children}</thead>,
    tbody: ({ children }) => <tbody>{children}</tbody>,
    tr: ({ children }) => <tr className="border-b border-gray-200">{children}</tr>,
    th: ({ children }) => (
      <th className="border border-gray-300 px-3 py-1.5 text-left font-semibold text-gray-700 bg-gray-100 whitespace-nowrap">
        {children}
      </th>
    ),
    td: ({ children }) => (
      <td className="border border-gray-200 px-3 py-1.5 text-gray-800">{children}</td>
    ),
    // Изображения (графики): клик открывает lightbox
    img: ({ src }) => (
      <img
        src={src}
        alt="График"
        className="max-w-full rounded-lg shadow-md mt-3 mb-2 border cursor-zoom-in hover:opacity-95 transition-opacity"
        onClick={() => setZoomedImage(src)}
      />
    ),
  };

  // Подписи для каждого типа шага агента
  const STATUS_LABELS = {
    thinking:             '🤔 Агент анализирует вопрос...',
    execute_sql_query:    '🔍 Выполняю SQL запрос...',
    execute_python_code:  '🐍 Генерирую график...',
    tool_result:          '✅ Обрабатываю результаты...',
  };

  // Обрабатывает выбор CSV-файла через скрытый input
  const handleUpload = async (e) => {
    const file = e.target.files[0];
    // Сбрасываем input — чтобы повторная загрузка того же файла сработала
    e.target.value = '';
    if (!file) return;

    if (!file.name.endsWith('.csv')) {
      setMessages(prev => [...prev, { role: 'system', content: 'Ошибка: можно загружать только файлы .csv' }]);
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      setMessages(prev => [...prev, { role: 'system', content: 'Ошибка: файл превышает лимит 10 МБ' }]);
      return;
    }

    setIsUploading(true);
    try {
      const response = await uploadCsv(file);
      const { table_name, columns, row_count, message } = response.data;
      setMessages(prev => [...prev, {
        role: 'system',
        content: `${message}\nСтолбцы: ${columns.join(', ')} | Строк: ${row_count}`
      }]);
    } catch (err) {
      const detail = err.response?.data?.detail ?? 'Ошибка загрузки файла';
      setMessages(prev => [...prev, { role: 'system', content: `Ошибка загрузки: ${detail}` }]);
    } finally {
      setIsUploading(false);
    }
  };

  const handleSend = async () => {
    if (!input.trim() || isLoading || !activeChatId) return;

    const userMessage = { role: 'user', content: input };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);
    setStatusText(STATUS_LABELS.thinking);

    const sentQuestion = input;

    try {
      await askAgentStream(activeChatId, sentQuestion, (event) => {
        if (event.type === 'thinking') {
          setStatusText(STATUS_LABELS.thinking);
        } else if (event.type === 'tool_call') {
          setStatusText(STATUS_LABELS[event.tool] ?? `🔧 Вызов ${event.tool}...`);
        } else if (event.type === 'tool_result') {
          setStatusText(STATUS_LABELS.tool_result);
        } else if (event.type === 'done') {
          setMessages(prev => [...prev, { role: 'agent', content: event.answer }]);
          // Обновляем заголовок чата в сайдбаре если это был первый вопрос
          setChats(prev => prev.map(c => {
            if (c.id === activeChatId && c.title === 'Новый чат') {
              return { ...c, title: sentQuestion.slice(0, 50) + (sentQuestion.length > 50 ? '...' : '') };
            }
            return c;
          }));
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
    <div className="flex h-full">

      {/* Sidebar — список чатов */}
      <aside className="w-64 flex-shrink-0 bg-gray-50 border-r border-gray-200 flex flex-col">
        {/* Кнопка нового чата */}
        <div className="p-3 border-b border-gray-200">
          <button
            onClick={handleNewChat}
            disabled={isLoading}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4"/>
            </svg>
            Новый чат
          </button>
        </div>

        {/* Список чатов */}
        <div className="flex-1 overflow-y-auto py-2">
          {chatsLoading ? (
            <p className="text-gray-400 text-xs text-center mt-4">Загрузка...</p>
          ) : (
            chats.map(chat => (
              <div
                key={chat.id}
                onClick={() => handleSelectChat(chat.id)}
                className={`group flex items-center justify-between mx-2 px-3 py-2 rounded-lg cursor-pointer transition-colors text-sm ${
                  chat.id === activeChatId
                    ? 'bg-emerald-50 text-emerald-700 font-medium'
                    : 'text-gray-600 hover:bg-gray-200 hover:text-gray-900'
                }`}
              >
                <span className="truncate flex-1 min-w-0">{chat.title}</span>
                {/* Кнопка удаления — видна при hover */}
                <button
                  onClick={(e) => handleDeleteChat(e, chat.id)}
                  className="ml-2 flex-shrink-0 opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500 transition-opacity"
                  title="Удалить чат"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"/>
                  </svg>
                </button>
              </div>
            ))
          )}
        </div>
      </aside>

      {/* Основная область чата */}
      <div className="flex flex-col flex-1 bg-white shadow-xl overflow-hidden">

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
              {msg.role === 'system' ? (
                // Системное сообщение (загрузка CSV) — по центру, синий стиль
                <div className="w-full flex justify-center">
                  <div className="max-w-2xl px-4 py-2 rounded-xl bg-blue-50 text-blue-700 border border-blue-200 text-sm text-center whitespace-pre-wrap">
                    {msg.content}
                  </div>
                </div>
              ) : (
                <div className={`max-w-3xl px-5 py-3 rounded-2xl shadow-sm ${
                  msg.role === 'user'
                    ? 'bg-emerald-600 text-white rounded-br-none'
                    : 'bg-white text-gray-800 border border-gray-100 rounded-bl-none'
                }`}>
                  {msg.role === 'user' ? (
                    // Сообщения пользователя — plain text
                    <span className="text-sm whitespace-pre-wrap">{msg.content}</span>
                  ) : (
                    // Ответы агента — рендерим markdown
                    <div className="text-sm max-w-none">
                      <ReactMarkdown components={markdownComponents}>
                        {prepareContent(msg.content)}
                      </ReactMarkdown>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}

          {/* Индикатор загрузки с текущим шагом агента */}
          {isLoading && (
            <div className="flex justify-start">
              <div className="bg-white border border-gray-100 text-gray-500 px-5 py-3 rounded-2xl rounded-bl-none shadow-sm flex items-center space-x-2">
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
                {statusText && <span className="text-sm ml-1">{statusText}</span>}
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="bg-white border-t border-gray-200 p-4 sticky bottom-0">
          <div className="flex items-end space-x-3 bg-gray-100 rounded-xl p-2 border border-gray-200 focus-within:border-emerald-500 focus-within:ring-1 focus-within:ring-emerald-500 transition-colors">
            {/* Скрытый input для файла */}
            <input
              type="file"
              accept=".csv"
              ref={fileInputRef}
              onChange={handleUpload}
              className="hidden"
            />

            {/* Кнопка загрузки CSV (скрепка) */}
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={isLoading || isUploading}
              title="Загрузить CSV файл"
              className="p-2 rounded-lg text-gray-500 hover:text-emerald-600 hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center flex-shrink-0"
            >
              {isUploading ? (
                <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
                </svg>
              ) : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"
                    d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.586-6.586a4 4 0 00-5.656-5.656L5.757 10.757a6 6 0 008.486 8.486L20 13"/>
                </svg>
              )}
            </button>

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

      {/* Lightbox — полноэкранный просмотр графика */}
      {zoomedImage && (
        <div
          className="fixed inset-0 bg-black/85 z-50 flex items-center justify-center cursor-zoom-out p-4"
          onClick={() => setZoomedImage(null)}
        >
          <img
            src={zoomedImage}
            alt="График"
            className="max-w-[92vw] max-h-[92vh] rounded-xl shadow-2xl object-contain"
            onClick={e => e.stopPropagation()}
          />
          {/* Кнопка закрытия */}
          <button
            className="absolute top-4 right-4 text-white/80 hover:text-white bg-black/40 rounded-full p-1.5 transition-colors"
            onClick={() => setZoomedImage(null)}
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"/>
            </svg>
          </button>
        </div>
      )}
    </div>
  );
}

export default Dashboard;
