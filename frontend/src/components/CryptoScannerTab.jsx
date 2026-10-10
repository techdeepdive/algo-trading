import React, { useState, useEffect } from 'react';
import { Loader2 } from 'lucide-react';

const CryptoScannerTab = ({ credentials }) => {
  const [engineState, setEngineState] = useState('idle');
  const [stats, setStats] = useState({});
  const [trades, setTrades] = useState([]);
  const [scannerState, setScannerState] = useState([]);
  const [loading, setLoading] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
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
  }, [refreshTrigger]);

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
  }, [refreshTrigger]);

  
  useEffect(() => {
    const fetchScannerState = async () => {
      try {
        const res = await fetch('/api/crypto/scanner_state');
        const data = await res.json();
        if (data.status === 'success') {
          setScannerState(data.scanner_state || []);
          setStats(data.stats || {});
        } else if (Array.isArray(data)) {
          setScannerState(data); // Fallback for old API if needed
        }
      } catch (e) {}
    };
    fetchScannerState();
    const intv = setInterval(fetchScannerState, 5000);
    return () => clearInterval(intv);
  }, [refreshTrigger]);

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

    
  const executeLiveTrade = async (symbol, signal, ltp) => {
    let finalSignal = signal;
    if (signal === 'NEUTRAL') {
      const manual = window.prompt(`Force trade for ${symbol} at ${ltp}?\nEnter 'LONG' or 'SHORT':`);
      if (manual && (manual.toUpperCase() === 'LONG' || manual.toUpperCase() === 'SHORT')) {
        finalSignal = manual.toUpperCase();
      } else {
        return;
      }
    } else {
      if (!window.confirm(`Execute ${signal} on ${symbol} at ${ltp}?`)) return;
    }

    try {
      const res = await fetch('/api/crypto/execute_trade', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, signal: finalSignal, ltp })
      });
      const data = await res.json();
      if (data.status === 'success') {
        alert(data.message);
        setRefreshTrigger(r => r + 1);
      } else {
        alert(data.message);
      }
    } catch (e) {
      alert("Failed to execute live trade");
    }
  };

  const clearCryptoData = async () => {
    if (!window.confirm("Are you sure you want to clear all crypto paper trades?")) return;
    try {
      const res = await fetch('/api/crypto/clear_trades', { method: 'POST' });
      const data = await res.json();
      if (data.status === 'success') setRefreshTrigger(r => r + 1);
      else alert(data.message);
    } catch (e) {
      alert("Failed to clear data");
    }
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
              onClick={clearCryptoData}
              className="px-4 py-2 bg-slate-800 hover:bg-slate-700 rounded-lg text-white font-medium text-sm transition-colors border border-slate-700"
            >
              Clear Data
            </button>
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

        <div className="grid grid-cols-7 gap-4 mb-6">
          <div className="bg-slate-950 border border-slate-800/50 rounded-lg p-4 flex flex-col justify-center">
            <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">Delta Balance</div>
            <div className="text-lg font-bold text-white">
              {balance !== null ? `₹${(parseFloat(balance) * 86.0).toFixed(2)} INR` : '-'}
            </div>
          </div>
          <div className="bg-slate-950 border border-slate-800/50 rounded-lg p-4 flex flex-col justify-center">
            <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">Engine</div>
            <div className={`text-lg font-bold ${engineState === 'running' ? 'text-emerald-400' : 'text-slate-400'}`}>
              {engineState === 'running' ? 'RUNNING' : 'STOPPED'}
            </div>
          </div>
          <div className="bg-slate-950 border border-slate-800/50 rounded-lg p-4 flex flex-col justify-center">
            <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">Last Sweep</div>
            <div className="text-md font-bold text-white truncate" title={stats.last_sweep || 'N/A'}>
              {stats.last_sweep ? stats.last_sweep.split(' ')[1] || stats.last_sweep : 'N/A'}
            </div>
          </div>
          <div className="bg-slate-950 border border-slate-800/50 rounded-lg p-4 flex flex-col justify-center">
            <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">Open/Closed</div>
            <div className="text-lg font-bold text-white">
              {stats.open_trades || 0} / {stats.closed_trades || 0}
            </div>
          </div>
          <div className="bg-slate-950 border border-slate-800/50 rounded-lg p-4 flex flex-col justify-center">
            <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">Capital Used</div>
            <div className="text-lg font-bold text-indigo-400">
              ₹{(stats.capital_used || 0).toLocaleString()}
            </div>
          </div>
          <div className="bg-slate-950 border border-slate-800/50 rounded-lg p-4 flex flex-col justify-center">
            <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">Live PNL</div>
            <div className={`text-lg font-bold ${stats.live_pnl_amt >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              ₹{(stats.live_pnl_amt || 0).toLocaleString()} <span className="text-xs opacity-70">({(stats.live_pnl_pct || 0).toFixed(2)}%)</span>
            </div>
          </div>
          <div className="bg-slate-950 border border-slate-800/50 rounded-lg p-4 flex flex-col justify-center">
            <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">Total PNL</div>
            <div className={`text-lg font-bold ${stats.total_pnl_amt >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              ₹{(stats.total_pnl_amt || 0).toLocaleString()} <span className="text-xs opacity-70">({(stats.total_pnl_pct || 0).toFixed(2)}%)</span>
            </div>
          </div>
        </div>

        
          <div className="mb-8">
            <h3 className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-3">Live Scanner State</h3>
            <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-950 border-y border-slate-800 text-slate-400 uppercase tracking-wider text-[10px] sticky top-0 z-10">
                  <tr>
                    <th className="px-4 py-2 font-semibold text-left">Symbol</th>
                    <th className="px-4 py-2 font-semibold text-left">Signal</th>
                    <th className="px-4 py-2 font-semibold text-right">LTP</th>
                    <th className="px-4 py-2 font-semibold text-right">WPR</th>
                    <th className="px-4 py-2 font-semibold text-right">5 EMA</th>
                    <th className="px-4 py-2 font-semibold text-right">15 EMA</th>
                    <th className="px-4 py-2 font-semibold text-right">50 EMA</th>
                    <th className="px-4 py-2 font-semibold text-right">Time</th>
                    <th className="px-4 py-2 font-semibold text-center">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/50">
                  {scannerState.length === 0 ? (
                    <tr>
                      <td colSpan="11" className="px-4 py-8 text-center text-slate-500 italic">
                        {engineState === 'running' ? 'Scanning crypto markets... Data will appear shortly.' : 'Engine stopped. Start engine to view live scanner state.'}
                      </td>
                    </tr>
                  ) : (
                  scannerState.map((s, i) => (
                    <tr key={i} className="hover:bg-slate-900/50 transition-colors text-xs">
                      <td className="px-4 py-2 font-bold text-white">{s.symbol}</td>
                      <td className={`px-4 py-2 font-bold ${s.signal === 'LONG' ? 'text-emerald-400' : s.signal === 'SHORT' ? 'text-rose-400' : 'text-slate-500'}`}>
                        {s.signal}
                      </td>
                      <td className="px-4 py-2 text-right text-slate-300 font-medium">${s.ltp ? s.ltp.toFixed(2) : '-'}</td>
                      <td className={`px-4 py-2 text-right font-medium ${s.wpr > -50 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {s.wpr ? s.wpr.toFixed(2) : '-'}
                      </td>
                      <td className="px-4 py-2 text-right text-indigo-300">{s.ema_fast ? s.ema_fast.toFixed(6) : '-'}</td>
                      <td className="px-4 py-2 text-right text-indigo-400">{s.ema_mid ? s.ema_mid.toFixed(6) : '-'}</td>
                      <td className="px-4 py-2 text-right text-slate-400">{s.ema_slow ? s.ema_slow.toFixed(6) : '-'}</td>
                      <td className="px-4 py-2 text-right text-slate-500">{s.timestamp}</td>
                      <td className="px-4 py-2 text-center">
                        <button
                          onClick={() => executeLiveTrade(s.symbol, s.signal, s.ltp)}
                          className={`px-3 py-1 rounded text-xs font-bold transition-colors ${
                            s.signal === 'LONG' ? 'bg-emerald-600 hover:bg-emerald-500 text-white' :
                            s.signal === 'SHORT' ? 'bg-rose-600 hover:bg-rose-500 text-white' :
                            'bg-indigo-600 hover:bg-indigo-500 text-white shadow shadow-indigo-500/20'
                          }`}
                        >
                          Live Trade
                        </button>
                      </td>
                    </tr>
                  )))}
                </tbody>
              </table>
            </div>
          </div>

        <h3 className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-3">Live Paper Trades</h3>
        <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-950 border-y border-slate-800 text-slate-400 uppercase tracking-wider text-[10px] sticky top-0 z-10">
              <tr>
                <th className="px-4 py-3 font-semibold text-left">Symbol</th>
                <th className="px-4 py-3 font-semibold text-left">Type</th>
                <th className="px-4 py-3 font-semibold text-right">Entry Time</th>
                <th className="px-4 py-3 font-semibold text-right">Entry Price</th>
                <th className="px-4 py-3 font-semibold text-right">Current Price</th>
                <th className="px-4 py-3 font-semibold text-right">Target (20%)</th>
                <th className="px-4 py-3 font-semibold text-right">SL (15%)</th>
                <th className="px-4 py-3 font-semibold text-center">Status</th>
                <th className="px-4 py-3 font-semibold text-right">PNL</th>
                <th className="px-4 py-3 font-semibold text-right">Exit Time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {trades.length === 0 ? (
                <tr>
                  <td colSpan="11" className="px-4 py-8 text-center text-slate-500 italic">
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
                    <td className="px-4 py-3 text-right font-medium text-slate-300">${t.entry_price ? t.entry_price.toFixed(6) : '0.000000'}</td>
                    <td className="px-4 py-3 text-right font-bold text-indigo-300">
                      ${t.current_price ? t.current_price.toFixed(2) : '-'}
                    </td>
                    <td className="px-4 py-3 text-right text-emerald-400 font-medium">${t.target ? t.target.toFixed(6) : '0.000000'}</td>
                    <td className="px-4 py-3 text-right text-rose-400 font-medium">${t.stop_loss ? t.stop_loss.toFixed(6) : '0.000000'}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`px-2 py-1 rounded-full text-[10px] font-bold ${
                        t.status === 'OPEN' ? 'bg-amber-500/20 text-amber-400' : 
                        t.status === 'CLOSED_TARGET' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-slate-700/50 text-slate-400'
                      }`}>
                        {t.status}
                      </span>
                    </td>
                    <td className={`px-4 py-3 text-right font-bold ${t.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      ₹{(t.pnl * 100).toFixed(2)} <span className="text-[10px] block opacity-70">{t.pnl >= 0 ? '+' : ''}{t.pnl ? t.pnl.toFixed(2) : '0.00'}%</span>
                    </td>
                    <td className="px-4 py-3 text-slate-500 text-right text-[10px]">{t.exit_time || '-'}</td>
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
