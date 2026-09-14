import React, { useState } from 'react';
import { Loader2 } from 'lucide-react';

export default function HomeTab({ credentials }) {
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState([]);
  const [error, setError] = useState(null);

  const runScan = async () => {
    if (!credentials.client_id || !credentials.access_token) {
      setError("Please provide Dhan credentials first.");
      return;
    }
    
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(credentials)
      });
      const data = await res.json();
      if (data.status === 'success') {
        setResults(data.results);
        if (data.startup_msg) {
          // Show as a temporary success message
          setError(data.startup_msg.includes('Failed') ? data.startup_msg : null);
          if (!data.startup_msg.includes('Failed')) {
             alert(data.startup_msg);
          }
        }
      } else {
        setError(data.message || "Failed to scan.");
      }
    } catch (e) {
      setError(e.toString());
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl shadow-xl overflow-hidden">
      <div className="p-5 border-b border-slate-800 flex justify-between items-center">
        <h2 className="text-lg font-semibold text-white">Scan Results</h2>
        <button 
          onClick={runScan}
          disabled={loading}
          className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors flex items-center gap-2"
        >
          <span>Run Scan</span>
          {loading && <Loader2 className="animate-spin w-4 h-4" />}
        </button>
      </div>

      {error && (
        <div className="p-4 m-4 bg-rose-500/10 border border-rose-500/40 rounded-lg text-rose-200 text-sm">
          {error}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm whitespace-nowrap">
          <thead className="bg-slate-800/50 text-slate-300">
            <tr>
              <th className="px-5 py-3 font-medium">Symbol</th>
              <th className="px-5 py-3 font-medium">LTP</th>
              <th className="px-5 py-3 font-medium">Trend (50 EMA)</th>
              <th className="px-5 py-3 font-medium">EMA Cross (5/15)</th>
              <th className="px-5 py-3 font-medium">William %R (70)</th>
              <th className="px-5 py-3 font-medium text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {results.length === 0 && !loading && (
              <tr>
                <td colSpan="6" className="px-5 py-8 text-center text-slate-500">
                  No scan results yet. Click "Run Scan" to fetch data.
                </td>
              </tr>
            )}
            {results.map((item, idx) => {
              const trend = item.ltp > item.ema50 ? 'UP' : 'DOWN';
              const emaCross = item.ema5 > item.ema15 ? 'BULLISH' : 'BEARISH';
              const wpr = item.wpr70;
              const action = item.signal === 'BULLISH' ? 'BUY' : item.signal === 'BEARISH' ? 'SELL' : 'NONE';
              return (
                <tr key={idx} className="hover:bg-slate-800/20 transition-colors">
                  <td className="px-5 py-4 font-semibold text-white">{item.symbol}</td>
                  <td className="px-5 py-4 font-mono text-slate-300">₹{item.ltp > 0 ? item.ltp : 'N/A'}</td>
                  <td className="px-5 py-4">
                    <span className={`px-2 py-1 rounded text-xs font-semibold ${trend === 'UP' ? 'bg-emerald-500/10 text-emerald-400' : trend === 'DOWN' ? 'bg-rose-500/10 text-rose-400' : 'bg-slate-500/10 text-slate-400'}`}>
                      {trend}
                    </span>
                  </td>
                  <td className="px-5 py-4">
                    <span className={`px-2 py-1 rounded text-xs font-semibold ${emaCross === 'BULLISH' ? 'bg-emerald-500/10 text-emerald-400' : emaCross === 'BEARISH' ? 'bg-rose-500/10 text-rose-400' : 'bg-slate-500/10 text-slate-400'}`}>
                      {emaCross}
                    </span>
                  </td>
                  <td className="px-5 py-4 font-mono text-slate-300">{wpr ? wpr.toFixed(2) : 'N/A'}</td>
                  <td className="px-5 py-4 text-right">
                    <span className={`px-3 py-1.5 rounded-md text-xs font-bold ${action === 'BUY' ? 'bg-emerald-600 text-white shadow-[0_0_10px_rgba(5,150,105,0.3)]' : action === 'SELL' ? 'bg-rose-600 text-white shadow-[0_0_10px_rgba(225,29,72,0.3)]' : 'bg-slate-700 text-slate-300'}`}>
                      {action}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
