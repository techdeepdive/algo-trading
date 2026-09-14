import React, { useState } from 'react';
import { Loader2, TrendingUp, TrendingDown, Minus } from 'lucide-react';

export default function NewsTab({ credentials }) {
  const [loading, setLoading] = useState(false);
  const [newsData, setNewsData] = useState([]);
  const [error, setError] = useState(null);

  const fetchNews = async () => {
    if (!credentials.gemini_key || !credentials.client_id) {
      setError("Please provide Gemini API Key and Dhan Client ID.");
      return;
    }
    
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/news', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(credentials)
      });
      const data = await res.json();
      if (data.status === 'success') {
        setNewsData(data.news);
      } else {
        setError(data.message || "Failed to fetch news.");
      }
    } catch (e) {
      setError(e.toString());
    } finally {
      setLoading(false);
    }
  };

  const getColor = (indicator) => {
    if (indicator === 'BULLISH') return 'emerald';
    if (indicator === 'BEARISH') return 'rose';
    return 'slate';
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl shadow-xl overflow-hidden mb-6">
      <div className="p-5 border-b border-slate-800 flex justify-between items-center bg-indigo-600/10">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2">
          Market News & AI Sentiment
        </h2>
        <button 
          onClick={fetchNews}
          disabled={loading}
          className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors flex items-center gap-2"
        >
          <span>Fetch Latest News</span>
          {loading && <Loader2 className="animate-spin w-4 h-4" />}
        </button>
      </div>
      
      <div className="p-5">
        {error && (
          <div className="p-4 mb-4 bg-rose-500/10 border border-rose-500/40 rounded-lg text-rose-200 text-sm">
            {error}
          </div>
        )}
        
        <div className="grid grid-cols-1 gap-4">
          {newsData.length === 0 && !loading && !error && (
            <div className="p-10 text-center text-slate-500 border border-dashed border-slate-700 rounded-xl">
              Click "Fetch Latest News" to scan top stocks and generate AI sentiment. (Requires Gemini API Key)
            </div>
          )}

          {newsData.map((item, idx) => {
            const c = getColor(item.indicator);
            return (
              <div key={idx} className={`p-4 rounded-xl border border-${c}-500/30 bg-${c}-500/10`}>
                <div className="flex justify-between items-start mb-3">
                  <div>
                    <h3 className="text-lg font-bold text-white">{item.symbol}</h3>
                    <div className="text-sm text-slate-400">LTP: ₹{item.ltp > 0 ? item.ltp : 'N/A'}</div>
                  </div>
                  <div className={`px-3 py-1 rounded-full text-xs font-bold bg-${c}-500/20 text-${c}-400 border border-${c}-500/30`}>
                    {item.indicator}
                  </div>
                </div>
                <div className={`mb-3 text-sm text-${c}-200 bg-slate-950/50 p-3 rounded border border-slate-800`}>
                  <span className="font-semibold block mb-1 text-slate-400">Gemini AI Analysis:</span>
                  {item.sentiment}
                </div>
                <ul className="list-disc pl-5 text-xs text-slate-400 space-y-1">
                  {item.headlines && item.headlines.map((h, i) => <li key={i}>{h}</li>)}
                </ul>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
