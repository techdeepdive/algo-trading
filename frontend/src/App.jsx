import React, { useState, useEffect } from 'react';
import { Home, Clock, Activity, Newspaper, ShieldCheck } from 'lucide-react';
import HomeTab from './components/HomeTab';
import HistoricalTab from './components/HistoricalTab';
import BacktestTab from './components/BacktestTab';
import HedgingTab from './components/HedgingTab';
import NewsTab from './components/NewsTab';

function App() {
  const [activeTab, setActiveTab] = useState('home');
  const [credentials, setCredentials] = useState({
    client_id: '',
    access_token: '',
    tg_bot: '',
    tg_chat: '',
    gemini_key: ''
  });

  useEffect(() => {
    const saved = localStorage.getItem('algo_creds');
    if (saved) {
      setCredentials(JSON.parse(saved));
    }
  }, []);

  const handleCredChange = (e) => {
    const newCreds = { ...credentials, [e.target.name]: e.target.value };
    setCredentials(newCreds);
    localStorage.setItem('algo_creds', JSON.stringify(newCreds));
  };

  const tabs = [
    { id: 'home', label: 'Home', icon: Home },
    { id: 'historical', label: 'Historical Data', icon: Clock },
    { id: 'backtest', label: 'Backtesting', icon: Activity },
    { id: 'hedging', label: 'Hedging', icon: ShieldCheck },
    { id: 'news', label: 'Market News (AI)', icon: Newspaper },
  ];

  return (
    <div className="max-w-7xl mx-auto p-6 space-y-6">
      <header className="flex justify-between items-center pb-4 border-b border-slate-800">
        <div className="flex items-center gap-4">
          <div className="w-11 h-11 bg-indigo-600 rounded-xl shadow-lg border border-slate-700 flex items-center justify-center text-white font-bold text-xl">
            A
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Algo Trading Dashboard</h1>
        </div>
      </header>

      <nav className="flex gap-0 border-b border-slate-800 overflow-x-auto">
        {tabs.map(tab => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`tab-btn px-4 py-3 text-sm font-medium border-b-2 flex items-center gap-2 whitespace-nowrap ${
                isActive 
                  ? 'active border-indigo-500 text-indigo-400' 
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          );
        })}
      </nav>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <div className="lg:col-span-1">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl sticky top-6">
            <h2 className="text-base font-semibold text-white mb-4">Credentials</h2>
            <div className="space-y-3">
              {[
                { name: 'client_id', label: 'Dhan Client ID *', placeholder: 'e.g. 1100XXXX' },
                { name: 'access_token', label: 'Dhan Access Token *', placeholder: 'Paste your token', type: 'password' },
                { separator: true },
                { name: 'tg_bot', label: 'Telegram Bot Token', placeholder: 'From @BotFather', type: 'password' },
                { name: 'tg_chat', label: 'Telegram Chat ID', placeholder: 'Your Chat ID', type: 'password' },
                { separator: true },
                { name: 'gemini_key', label: 'Gemini API Key', placeholder: 'AI News Hub access...', type: 'password' }
              ].map((field, idx) => field.separator ? (
                <hr key={`hr-${idx}`} className="border-slate-800 my-3" />
              ) : (
                <div key={field.name}>
                  <label className="block text-xs font-medium text-slate-400 mb-1">{field.label}</label>
                  <input 
                    type={field.type || "text"}
                    name={field.name}
                    value={credentials[field.name] || ''}
                    onChange={handleCredChange}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors" 
                    placeholder={field.placeholder}
                  />
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="lg:col-span-3">
          {activeTab === 'home' && <HomeTab credentials={credentials} />}
          {activeTab === 'historical' && <HistoricalTab credentials={credentials} />}
          {activeTab === 'backtest' && <BacktestTab credentials={credentials} />}
          {activeTab === 'hedging' && <HedgingTab credentials={credentials} />}
          {activeTab === 'news' && <NewsTab credentials={credentials} />}
        </div>
      </div>
    </div>
  );
}

export default App;
