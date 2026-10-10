import React, { useState, useEffect } from 'react';
import { Loader2 } from 'lucide-react';

const CryptoScannerTab = ({ credentials }) => {
  const [engineState, setEngineState] = useState('idle');
  const [trades, setTrades] = useState([]);
  const [scannerState, setScannerState] = useState([]);
  const [loading, setLoading] = useState(false);
  const [balance, setBalance] = useState(null);

  useEffect(() => {
    const fetchState = async () => {
      try {
        const res = await fetch('/api/crypto/state');
        const data = await res.json();
        setEngineState(data.status);
      } catch (e) {
        console.error(e);
      }
    };
    fetchState();
    const intv = setInterval(fetchState, 5000);
    return () => clearInterval(intv);
  }, []);

  useEffect(() => {
    const fetchTrades = async () => {
      try {
        const res = await fetch('/api/crypto/trades');
        const data = await res.json();
        if (Array.isArray(data)) {
          setTrades(data);
        }
      } catch (e) {
        console.error(e);
      }
    };
    fetchTrades();
    const intv = setInterval(fetchTrades, 5000);
    return () => clearInterval(intv);
  }, []);

  
  useEffect(() => {
    const fetchScannerState = async () => {
      try {
        const res = await fetch('/api/crypto/scanner_state');
        const data = await res.json();
        if (Array.isArray(data)) setScannerState(data);
      } catch (e) {}
    };
    fetchScannerState();
    const intv = setInterval(fetchScannerState, 5000);
    return () => clearInterval(intv);
  }, []);

  const fetchBalance = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/crypto/balance', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({delta_api_key: credentials.delta_api_key, delta_api_secret: credentials.delta_api_secret})
      });
      const data = await res.json();
      if(data.status === 'success') {
        setBalance(data.balance);
      } else {
        alert(data.message);
      }
    } catch (e) {
      alert("Error fetching balance");
    }
    setLoading(false);
  };

  const startEngine = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/crypto/start', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          delta_api_key: credentials.delta_api_key, 
          delta_api_secret: credentials.delta_api_secret,
          tg_bot: credentials.tg_bot,
          tg_chat: credentials.tg_chat
        })
      });
      const data = await res.json();
      if(data.status === 'success') {
        setEngineState('running');
      } else {
        alert(data.message);
      }
    } catch(e) {
      alert("Error starting engine");
    }
    setLoading(false);
  };

  const stopEngine = async () => {
    try {
      await fetch('/api/crypto/stop', {method: 'POST'});
      setEngineState('idle');
    } catch(e) {}
  };

  const livePnl = trades.filter(t => t.status === 'OPEN').reduce((acc, t) => acc + (t.pnl || 0), 0);
  const totalPnl = trades.reduce((acc, t) => acc + (t.pnl || 0), 0);

  return (
    <div className="space-y-6">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl relative overflow-hidden">
        
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            Crypto Scanner (Delta Exchange)
            <span className={`text-[10px] px-2 py-1 rounded-full font-bold uppercase tracking-wider ${
              engineState === 'running' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' :
              'bg-amber-500/20 text-amber-400 border border-amber-500/30'
            }`}>
              {engineState}
            </span>
          </h2>
          <div className="flex gap-2">
            <button 
              onClick={fetchBalance}
              disabled={loading}
              className="px-4 py-2 bg-slate-800 hover:bg-slate-700 rounded-lg text-white font-medium text-sm transition-colors border border-slate-700"
            >
              Get Balance
            </button>
            {engineState !== 'running' ? (
              <button 
                onClick={startEngine}
                disabled={loading}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-white font-medium text-sm transition-colors shadow-lg shadow-indigo-500/20 flex items-center gap-2"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                Start Engine
              </button>
            ) : (
              <button 
                onClick={stopEngine}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-500 rounded-lg text-white font-medium text-sm transition-colors shadow-lg shadow-rose-500/20"
              >
                Stop Engine
              </button>
            )}
          </div>
        </div>

        <div className="grid grid-cols-4 gap-4 mb-6">
          <div className="bg-slate-950 border border-slate-800/50 rounded-lg p-4">
            <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">Delta Balance</div>
            <div className="text-lg font-bold text-white">
              {balance !== null ? `${balance} USDT` : '-'}
            </div>
          </div>
          <div className="bg-slate-950 border border-slate-800/50 rounded-lg p-4">
            <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">Open Trades</div>
            <div className="text-lg font-bold text-white">{trades.filter(t => t.status === 'OPEN').length}</div>
          </div>
          <div className="bg-slate-950 border border-slate-800/50 rounded-lg p-4">
            <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">Live PNL %</div>
            <div className={`text-lg font-bold ${livePnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {livePnl > 0 ? '+' : ''}{livePnl.toFixed(2)}%
            </div>
          </div>
          <div className="bg-slate-950 border border-slate-800/50 rounded-lg p-4">
            <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">Total PNL %</div>
            <div className={`text-lg font-bold ${totalPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {totalPnl > 0 ? '+' : ''}{totalPnl.toFixed(2)}%
            </div>
          </div>
        </div>

        
        {scannerState.length > 0 && (
          <div className="mb-8">
            <h3 className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-3">Live Scanner State</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-950/50 border-y border-slate-800 text-slate-400 uppercase tracking-wider text-[10px]">
                  <tr>
                    <th className="px-4 py-2 font-semibold text-left">Symbol</th>
                    <th className="px-4 py-2 font-semibold text-left">Signal</th>
                    <th className="px-4 py-2 font-semibold text-right">LTP</th>
                    <th className="px-4 py-2 font-semibold text-right">WPR</th>
                    <th className="px-4 py-2 font-semibold text-right">5 EMA</th>
                    <th className="px-4 py-2 font-semibold text-right">15 EMA</th>
                    <th className="px-4 py-2 font-semibold text-right">50 EMA</th>
                    <th className="px-4 py-2 font-semibold text-right">Time</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/50">
                  {scannerState.map((s, i) => (
                    <tr key={i} className="hover:bg-slate-900/50 transition-colors text-xs">
                      <td className="px-4 py-2 font-bold text-white">{s.symbol}</td>
                      <td className={`px-4 py-2 font-bold ${s.signal === 'LONG' ? 'text-emerald-400' : s.signal === 'SHORT' ? 'text-rose-400' : 'text-slate-500'}`}>
                        {s.signal}
                      </td>
                      <td className="px-4 py-2 text-right text-slate-300 font-medium">${s.ltp ? s.ltp.toFixed(2) : '-'}</td>
                      <td className={`px-4 py-2 text-right font-medium ${s.wpr > -50 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {s.wpr ? s.wpr.toFixed(2) : '-'}
                      </td>
                      <td className="px-4 py-2 text-right text-indigo-300">{s.ema_fast ? s.ema_fast.toFixed(2) : '-'}</td>
                      <td className="px-4 py-2 text-right text-indigo-400">{s.ema_mid ? s.ema_mid.toFixed(2) : '-'}</td>
                      <td className="px-4 py-2 text-right text-slate-400">{s.ema_slow ? s.ema_slow.toFixed(2) : '-'}</td>
                      <td className="px-4 py-2 text-right text-slate-500">{s.timestamp}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <h3 className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-3">Live Paper Trades</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-950/50 border-y border-slate-800 text-slate-400 uppercase tracking-wider text-[10px]">
              <tr>
                <th className="px-4 py-3 font-semibold text-left">Symbol</th>
                <th className="px-4 py-3 font-semibold text-left">Type</th>
                <th className="px-4 py-3 font-semibold text-right">Entry Time</th>
                <th className="px-4 py-3 font-semibold text-right">Entry Price</th>
                <th className="px-4 py-3 font-semibold text-right">Current Price</th>
                <th className="px-4 py-3 font-semibold text-right">Target (20%)</th>
                <th className="px-4 py-3 font-semibold text-right">SL (15%)</th>
                <th className="px-4 py-3 font-semibold text-center">Status</th>
                <th className="px-4 py-3 font-semibold text-right">PNL %</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {trades.length === 0 ? (
                <tr>
                  <td colSpan="9" className="px-4 py-8 text-center text-slate-500 italic">
                    No crypto trades executed yet. Start the engine to scan for signals.
                  </td>
                </tr>
              ) : (
                trades.map((t) => (
                  <tr key={t.id} className="hover:bg-slate-900/50 transition-colors">
                    <td className="px-4 py-3 font-bold text-white">{t.symbol}</td>
                    <td className={`px-4 py-3 font-bold ${t.trade_type === 'LONG' ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {t.trade_type}
                    </td>
                    <td className="px-4 py-3 text-slate-400 text-right">{t.entry_time}</td>
                    <td className="px-4 py-3 text-right font-medium text-slate-300">${t.entry_price ? t.entry_price.toFixed(2) : '0.00'}</td>
                    <td className="px-4 py-3 text-right font-bold text-indigo-300">
                      ${t.current_price ? t.current_price.toFixed(2) : '-'}
                    </td>
                    <td className="px-4 py-3 text-right text-emerald-400 font-medium">${t.target ? t.target.toFixed(2) : '0.00'}</td>
                    <td className="px-4 py-3 text-right text-rose-400 font-medium">${t.stop_loss ? t.stop_loss.toFixed(2) : '0.00'}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`px-2 py-1 rounded-full text-[10px] font-bold ${
                        t.status === 'OPEN' ? 'bg-amber-500/20 text-amber-400' : 
                        t.status === 'CLOSED_TARGET' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-slate-700/50 text-slate-400'
                      }`}>
                        {t.status}
                      </span>
                    </td>
                    <td className={`px-4 py-3 text-right font-bold ${t.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {t.pnl >= 0 ? '+' : ''}{t.pnl ? t.pnl.toFixed(2) : '0.00'}%
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

      </div>
    </div>
  );
};

export default CryptoScannerTab;
