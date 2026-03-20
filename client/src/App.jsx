import { BrowserRouter as Router, Routes, Route, Navigate, Link } from 'react-router-dom';
import { useState } from 'react';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import Dashboard from './pages/Dashboard';

function App() {
  const [isAuth, setIsAuth] = useState(!!localStorage.getItem('token'));

  const handleLogout = () => {
    localStorage.removeItem('token');
    setIsAuth(false);
    window.location.href = '/login';
  };

  return (
    <Router>
      <div className="min-h-screen bg-gray-50 font-sans text-gray-900 antialiased">
        
        {/* Top Navigation Bar */}
        <header className="w-full bg-white border-b border-gray-200 sticky top-0 z-50">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <div className="flex items-center">
              <Link to="/" className="text-xl font-bold text-gray-900 hover:text-emerald-600 transition-colors">
                LLM Agent
              </Link>
            </div>
            
            <div className="flex items-center space-x-4">
              {isAuth ? (
                <>
                  <Link to="/dashboard" className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors">
                    Dashboard
                  </Link>
                  <button 
                    onClick={handleLogout} 
                    className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
                  >
                    Log out
                  </button>
                </>
              ) : (
                <>
                  <Link to="/login" className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors">
                    Log in
                  </Link>
                  <Link 
                    to="/register" 
                    className="px-4 py-2 text-sm font-medium text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg transition-colors shadow-sm"
                  >
                    Sign up
                  </Link>
                </>
              )}
            </div>
          </div>
        </header>

        {/* Main Content Area */}
        <main className="flex-1">
          <Routes>
            <Route path="/" element={isAuth ? <Navigate to="/dashboard" /> : <PublicHome />} />
            <Route path="/login" element={<LoginPage setIsAuth={setIsAuth} />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route 
              path="/dashboard" 
              element={isAuth ? <Dashboard /> : <Navigate to="/login" />} 
            />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

function PublicHome() {
  return (
    <div className="flex flex-col items-center justify-center h-[calc(100vh-4rem)] text-center px-4">
      <div className="max-w-2xl">
        <h1 className="text-4xl sm:text-5xl font-extrabold text-gray-900 tracking-tight mb-6">
          Ваш <span className="text-emerald-600">AI-аналитик</span> данных
        </h1>
        <p className="text-lg text-gray-600 mb-8">
          Задавайте вопросы на естественном языке и получайте ответы, графики и SQL-запросы мгновенно.
        </p>
        <div className="flex justify-center gap-4">
          <Link 
            to="/register" 
            className="px-6 py-3 text-base font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded-xl transition-all shadow-lg hover:shadow-emerald-200"
          >
            Начать бесплатно
          </Link>
          <Link 
            to="/login" 
            className="px-6 py-3 text-base font-semibold text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 rounded-xl transition-all"
          >
            Уже есть аккаунт
          </Link>
        </div>
      </div>
    </div>
  );
}

export default App;