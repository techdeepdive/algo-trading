import React, { useState, useEffect } from 'react';
import { Play, Square, Loader2, RefreshCw } from 'lucide-react';

export default function ScannerTab({ credentials }) {
  const [loading, setLoading] = useState(false);
  const [engineRunning, setEngineRunning] = useState(false);
  const [engineStatus, setEngineStatus] = useState('STOPPED');
  const [scanState, setScanState] = useState([]);
  const [trades, setTrades] = useState([]);
  const [error, setError] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [tradeForm, setTradeForm] = useState(null);
  const [selectedStrategy, setSelectedStrategy] = useState('WPR_CROSS_EMA');
  const [watchlists, setWatchlists] = useState(['nifty50']);
  const [customSymbols, setCustomSymbols] = useState('');

  // Poll state every 5 seconds
  useEffect(() => {
    const fetchState = async () => {
      try {
        const res = await fetch('/api/algoscan/state');
        const data = await res.json();
        if (data.status === 'success') {
          setEngineRunning(data.is_running);
          setEngineStatus(data.engine_status || (data.is_running ? 'RUNNING' : 'STOPPED'));
          setScanState(data.scan_state || []);
          setTrades(data.trades || []);
          setError(null);
        }
      } catch (err) {
        console.error("Error fetching state", err);
      }
    };

    fetchState();
    const interval = setInterval(fetchState, 5000);
    return () => clearInterval(interval);
  }, []);

  const toggleEngine = async () => {
    if (!credentials.client_id || !credentials.dhan_pin || !credentials.dhan_totp) {
      setError("Please save Dhan credentials in the Setup tab first.");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const endpoint = engineRunning ? '/api/algoscan/stop' : '/api/algoscan/start';
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: credentials.client_id,
          dhan_pin: credentials.dhan_pin, dhan_totp: credentials.dhan_totp,
          tg_bot: credentials.tg_bot,
          tg_chat: credentials.tg_chat,
          strategy_name: selectedStrategy,
          watchlists: watchlists,
          custom_symbols: customSymbols
        })
      });
      const data = await res.json();
      if (data.status === 'success') {
        setEngineRunning(!engineRunning);
      } else {
        setError(data.message);
      }
    } catch (err) {
      setError(err.toString());
    } finally {
      setLoading(false);
    }
  };

  const openTradeModal = (symbol, ltp, trade_type) => {
    // Helper to round to nearest 0.05
    const rt = (price) => Math.round(price / 0.05) * 0.05;
    
    let limit = trade_type === 'LONG' ? rt(ltp * 1.005) : rt(ltp * 0.995);
    let sl = trade_type === 'LONG' ? rt(limit * 0.97) : rt(limit * 1.03);
    let tgt = trade_type === 'LONG' ? rt(limit * 1.03) : rt(limit * 0.97);
    
    setTradeForm({
      symbol,
      trade_type,
      qty: Math.max(1, Math.floor(10000 / ltp)),
      price: limit.toFixed(2),
      sl: sl.toFixed(2),
      tgt: tgt.toFixed(2),
      product_type: 'MIS',
      is_amo: false
    });
    setShowModal(true);
  };

  const submitTrade = async () => {
    if (!credentials.client_id || !credentials.dhan_pin || !credentials.dhan_totp) {
      setError("Please save Dhan credentials in the Setup tab first.");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch('/api/algoscan/trade', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: credentials.client_id,
          dhan_pin: credentials.dhan_pin, dhan_totp: credentials.dhan_totp,
          tg_bot: credentials.tg_bot,
          tg_chat: credentials.tg_chat,
          symbol: tradeForm.symbol,
          trade_type: tradeForm.trade_type,
          qty: parseInt(tradeForm.qty),
          price: parseFloat(tradeForm.price),
          sl: parseFloat(tradeForm.sl),
          tgt: parseFloat(tradeForm.tgt),
          product_type: tradeForm.product_type,
          is_amo: tradeForm.is_amo
        })
      });
      const data = await res.json();
      if (data.status === 'success') {
        alert(data.message);
        setShowModal(false);
      } else {
        alert('Trade failed: ' + data.message);
      }
    } catch (err) {
      alert('Trade failed: ' + err.toString());
    } finally {
      setLoading(false);
    }
  };

  const clearDatabase = async (force = false) => {
    if (!force && !window.confirm("Are you sure you want to clear all scanner data and paper trades?")) return;
    try {
      await fetch('/api/algoscan/clear', { method: 'POST' });
      setScanState([]);
      setTrades([]);
    } catch (err) {
      console.error(err);
    }
  };



  // Metrics calculation
  const openTrades = trades.filter(t => t.status === 'OPEN');
  const closedTrades = trades.filter(t => t.status !== 'OPEN');
  
  const livePnl = openTrades.reduce((acc, t) => acc + (t.pnl || 0), 0);
  const totalCapitalUsed = openTrades.reduce((acc, t) => acc + ((t.spot_entry || 0) * (t.premium_entry || 0)), 0);
  const bookedPnl = closedTrades.reduce((acc, t) => acc + (t.pnl || 0), 0);
  const totalPnl = livePnl + bookedPnl;
  
  let lastSweep = "N/A";
  if (scanState.length > 0) {
     const times = scanState.map(s => new Date(s.last_updated).getTime());
     const maxTime = new Date(Math.max(...times));
     lastSweep = maxTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }
  const formatDate = (isoStr) => {
    if (!isoStr) return '-';
    try {
      const d = new Date(isoStr);
      if (isNaN(d.getTime())) return isoStr;
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) + ' ' + d.toLocaleDateString([], { month: 'short', day: 'numeric' });
    } catch { return '-'; }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl shadow-xl overflow-hidden">
      <div className="p-6">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
          <div>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              Live Trade / Scanner
            </h2>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <select 
                value={selectedStrategy}
                onChange={(e) => setSelectedStrategy(e.target.value)}
                className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-indigo-500"
              >
                <option value="WPR_CROSS_EMA">WPR + 5/15 EMA Crossover</option>
                <option value="RSI_MR">RSI Mean Reversion</option>
                <option value="BB_BREAKOUT">Bollinger Breakout</option>
                <option value="OI_BREAKOUT">OI Spike Breakout (Mocked)</option>
              </select>
              
              <div className="flex items-center gap-2">
                <label className="text-xs text-slate-400 flex items-center gap-1 cursor-pointer hover:text-slate-300">
                  <input type="checkbox" checked={watchlists.includes('nifty50')} onChange={(e) => {
                    if (e.target.checked) setWatchlists([...watchlists, 'nifty50']);
                    else setWatchlists(watchlists.filter(w => w !== 'nifty50'));
                  }} className="rounded bg-slate-800 border-slate-700 text-indigo-500" />
                  Nifty 50
                </label>
                <label className="text-xs text-slate-400 flex items-center gap-1 cursor-pointer hover:text-slate-300">
                  <input type="checkbox" checked={watchlists.includes('banknifty')} onChange={(e) => {
                    if (e.target.checked) setWatchlists([...watchlists, 'banknifty']);
                    else setWatchlists(watchlists.filter(w => w !== 'banknifty'));
                  }} className="rounded bg-slate-800 border-slate-700 text-indigo-500" />
                  BankNifty
                </label>
                <label className="text-xs text-slate-400 flex items-center gap-1 cursor-pointer hover:text-slate-300">
                  <input type="checkbox" checked={watchlists.includes('mcx')} onChange={(e) => {
                    if (e.target.checked) setWatchlists([...watchlists, 'mcx']);
                    else setWatchlists(watchlists.filter(w => w !== 'mcx'));
                  }} className="rounded bg-slate-800 border-slate-700 text-indigo-500" />
                  MCX
                </label>
              </div>

              <input 
                type="text"
                placeholder="Custom (e.g. TCS, INFY)"
                value={customSymbols}
                onChange={(e) => setCustomSymbols(e.target.value)}
                className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-indigo-500 w-40 placeholder-slate-500"
              />
            </div>
          </div>
          <div className="flex gap-3">
            <button
              onClick={clearDatabase}
              className="px-4 py-2 rounded-lg text-sm font-bold bg-slate-800 text-slate-300 hover:bg-slate-700 transition-colors"
            >
              Clear Data
            </button>
            <button 
              onClick={toggleEngine}
              disabled={loading}
              className={`px-4 py-2 rounded-lg text-sm font-bold flex items-center gap-2 transition-colors ${
                engineRunning 
                  ? 'bg-rose-500/20 text-rose-400 hover:bg-rose-500/30 border border-rose-500/50' 
                  : 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 border border-emerald-500/50'
              }`}
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : (engineRunning ? <Square className="w-4 h-4" /> : <Play className="w-4 h-4" />)}
              {engineRunning ? 'Stop Engine' : 'Start Engine'}
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-6 p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 text-sm">
            {error}
          </div>
        )}

        {/* Top Metric Panels */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4 mb-8">
          <div className="bg-slate-950 rounded-xl border border-slate-800 p-4 shadow-inner">
            <div className="text-xs font-semibold text-slate-500 mb-1 uppercase tracking-wider">Engine</div>
            <div className={`text-lg font-bold flex items-center gap-2 ${engineStatus === 'RUNNING' ? 'text-emerald-400' : engineStatus === 'PAUSED' ? 'text-amber-400' : 'text-slate-400'}`}>
              {engineStatus === 'RUNNING' && <RefreshCw className="w-4 h-4 animate-spin" />}
              {engineStatus === 'PAUSED' ? 'PAUSED (Market Closed)' : engineStatus}
            </div>
          </div>
          <div className="bg-slate-950 rounded-xl border border-slate-800 p-4 shadow-inner">
            <div className="text-xs font-semibold text-slate-500 mb-1 uppercase tracking-wider">Last Sweep</div>
            <div className="text-lg font-bold text-white">{lastSweep}</div>
          </div>
          <div className="bg-slate-950 rounded-xl border border-slate-800 p-4 shadow-inner">
            <div className="text-xs font-semibold text-slate-500 mb-1 uppercase tracking-wider">Open Trades</div>
            <div className="text-lg font-bold text-white">{openTrades.length}</div>
          </div>
          <div className="bg-slate-950 rounded-xl border border-slate-800 p-4 shadow-inner">
            <div className="text-xs font-semibold text-slate-500 mb-1 uppercase tracking-wider">Closed Trades</div>
            <div className="text-lg font-bold text-slate-400">{closedTrades.length}</div>
          </div>
          <div className="bg-slate-950 rounded-xl border border-slate-800 p-4 shadow-inner">
            <div className="text-xs font-semibold text-slate-500 mb-1 uppercase tracking-wider">Capital Used</div>
            <div className="text-lg font-bold text-indigo-400">
              ₹{totalCapitalUsed.toFixed(2)}
            </div>
          </div>
          <div className="bg-slate-950 rounded-xl border border-slate-800 p-4 shadow-inner">
            <div className="text-xs font-semibold text-slate-500 mb-1 uppercase tracking-wider">Live PNL</div>
            <div className={`text-lg font-bold ${livePnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              ₹{livePnl.toFixed(2)}
            </div>
          </div>
          <div className="bg-slate-950 rounded-xl border border-slate-800 p-4 shadow-inner">
            <div className="text-xs font-semibold text-slate-500 mb-1 uppercase tracking-wider">Total PNL</div>
            <div className={`text-lg font-bold ${totalPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              ₹{totalPnl.toFixed(2)}
            </div>
          </div>
        </div>

        {/* Paper Trades Table */}
        <h3 className="text-sm font-bold text-white mb-3 mt-8">Live Paper Trades</h3>
        <div className="bg-slate-950 rounded-xl border border-slate-800 overflow-x-auto mb-8">
          <table className="w-full text-left text-xs whitespace-nowrap">
            <thead className="bg-slate-900 border-b border-slate-800 text-slate-400 uppercase tracking-wider">
              <tr>
                <th className="px-4 py-3 font-semibold">Symbol</th>
                <th className="px-4 py-3 font-semibold">Type</th>
                <th className="px-4 py-3 font-semibold">Instrument</th>
                <th className="px-4 py-3 font-semibold">Entry Time</th>
                <th className="px-4 py-3 font-semibold text-right">Entry Price</th>
                <th className="px-4 py-3 font-semibold text-right">Current Price</th>
                <th className="px-4 py-3 font-semibold text-right">Qty</th>
                <th className="px-4 py-3 font-semibold text-right">Stop Loss</th>
                <th className="px-4 py-3 font-semibold text-right">Target</th>
                <th className="px-4 py-3 font-semibold text-center">Status</th>
                <th className="px-4 py-3 font-semibold text-right">Live PNL</th>
                <th className="px-4 py-3 font-semibold text-center">Exit Time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {trades.length === 0 ? (
                <tr>
                  <td colSpan="12" className="px-4 py-8 text-center text-slate-500 italic">
                    No paper trades executed yet. Start the engine to scan for signals.
                  </td>
                </tr>
              ) : (
                trades.map((t) => (
                  <tr key={t.id} className="hover:bg-slate-900/50 transition-colors">
                    <td className="px-4 py-3 font-bold text-white">{t.symbol}</td>
                    <td className={`px-4 py-3 font-bold ${t.trade_type === 'LONG' ? 'text-indigo-400' : 'text-rose-400'}`}>
                      {t.trade_type}
                    </td>
                    <td className="px-4 py-3 text-slate-300">{t.option_symbol}</td>
                    <td className="px-4 py-3 text-slate-400">{formatDate(t.entry_time)}</td>
                    <td className="px-4 py-3 text-right">₹{t.spot_entry.toFixed(2)}</td>
                    <td className="px-4 py-3 text-right font-bold text-indigo-300">
                      {t.status === 'OPEN' && t.current_price ? `₹${t.current_price.toFixed(2)}` : (t.exit_premium ? `₹${t.exit_premium.toFixed(2)}` : '-')}
                    </td>
                    <td className="px-4 py-3 text-right font-medium">{t.premium_entry}</td>
                    <td className="px-4 py-3 text-right text-rose-400 font-medium">₹{t.stop_loss.toFixed(2)}</td>
                    <td className="px-4 py-3 text-right text-emerald-400 font-medium">₹{t.target.toFixed(2)}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`px-2 py-1 rounded-full text-[10px] font-bold ${
                        t.status === 'OPEN' ? 'bg-amber-500/20 text-amber-400' : 
                        t.status === 'CLOSED_TARGET' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-slate-700/50 text-slate-400'
                      }`}>
                        {t.status}
                      </span>
                    </td>
                    <td className={`px-4 py-3 text-right font-bold ${t.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {t.pnl >= 0 ? '+' : ''}₹{t.pnl.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-center text-slate-400">{formatDate(t.exit_time)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Scanner State Table */}
        <h3 className="text-sm font-bold text-white mb-3">Scanner State</h3>
        <div className="bg-slate-950 rounded-xl border border-slate-800 overflow-x-auto max-h-[400px]">
          <table className="w-full text-left text-xs whitespace-nowrap">
            <thead className="bg-slate-900 sticky top-0 border-b border-slate-800 text-slate-400 uppercase tracking-wider">
              <tr>
                <th className="px-4 py-3 font-semibold">Stock</th>
                <th className="px-4 py-3 font-semibold text-right">LTP</th>
                {selectedStrategy === 'WPR_CROSS_EMA' && (
                  <>
                    <th className="px-4 py-3 font-semibold text-right">WPR(70)</th>
                    <th className="px-4 py-3 font-semibold text-right">5 EMA</th>
                    <th className="px-4 py-3 font-semibold text-right">15 EMA</th>
                    <th className="px-4 py-3 font-semibold text-center">Trend</th>
                  </>
                )}
                {selectedStrategy === 'RSI_MR' && (
                  <>
                    <th className="px-4 py-3 font-semibold text-right">RSI(14)</th>
                    <th className="px-4 py-3 font-semibold text-right">-</th>
                    <th className="px-4 py-3 font-semibold text-right">-</th>
                    <th className="px-4 py-3 font-semibold text-center">Trend</th>
                  </>
                )}
                {selectedStrategy === 'BB_BREAKOUT' && (
                  <>
                    <th className="px-4 py-3 font-semibold text-right">Close</th>
                    <th className="px-4 py-3 font-semibold text-right">Upper BB</th>
                    <th className="px-4 py-3 font-semibold text-right">Lower BB</th>
                    <th className="px-4 py-3 font-semibold text-center">Trend</th>
                  </>
                )}
                {selectedStrategy === 'OI_BREAKOUT' && (
                  <>
                    <th className="px-4 py-3 font-semibold text-right">Ind 1</th>
                    <th className="px-4 py-3 font-semibold text-right">Ind 2</th>
                    <th className="px-4 py-3 font-semibold text-right">Ind 3</th>
                    <th className="px-4 py-3 font-semibold text-center">Trend</th>
                  </>
                )}
                <th className="px-4 py-3 font-semibold text-center">Signal</th>
                <th className="px-4 py-3 font-semibold text-center">Last Updated</th>
                <th className="px-4 py-3 font-semibold text-center">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {scanState.length === 0 ? (
                <tr>
                  <td colSpan="7" className="px-4 py-6 text-center text-slate-500 italic">
                    Waiting for first sweep...
                  </td>
                </tr>
              ) : (
                scanState.map((s) => {
                  const bullish_cross = s.ema_fast > s.ema_mid;
                  const cross_status = bullish_cross ? "FAST > MID" : "FAST < MID";
                  
                  return (
                    <tr key={s.symbol} className="hover:bg-slate-900/50 transition-colors">
                      <td className="px-4 py-2 font-bold text-white">{s.symbol}</td>
                      <td className="px-4 py-2 text-right">₹{s.ltp.toFixed(2)}</td>
                      {selectedStrategy === 'WPR_CROSS_EMA' && (
                        <>
                          <td className={`px-4 py-2 text-right font-medium ${s.wpr < -70 ? 'text-rose-400' : s.wpr > -20 ? 'text-emerald-400' : 'text-slate-300'}`}>
                            {s.wpr.toFixed(2)}
                          </td>
                          <td className="px-4 py-2 text-right text-slate-300">{s.ema_fast.toFixed(2)}</td>
                          <td className="px-4 py-2 text-right text-slate-300">{s.ema_mid.toFixed(2)}</td>
                          <td className="px-4 py-2 text-center">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${bullish_cross ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'}`}>
                              {cross_status}
                            </span>
                          </td>
                        </>
                      )}
                      
                      {selectedStrategy === 'RSI_MR' && (
                        <>
                          <td className={`px-4 py-2 text-right font-medium ${s.wpr > 70 ? 'text-rose-400' : s.wpr < 30 ? 'text-emerald-400' : 'text-slate-300'}`}>
                            {s.wpr.toFixed(2)}
                          </td>
                          <td className="px-4 py-2 text-right text-slate-500">-</td>
                          <td className="px-4 py-2 text-right text-slate-500">-</td>
                          <td className="px-4 py-2 text-center">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${s.wpr > 50 ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'}`}>
                              {s.wpr > 50 ? 'BULL' : 'BEAR'}
                            </span>
                          </td>
                        </>
                      )}
                      
                      {selectedStrategy === 'BB_BREAKOUT' && (
                        <>
                          <td className="px-4 py-2 text-right text-slate-300">{s.wpr.toFixed(2)}</td>
                          <td className="px-4 py-2 text-right text-slate-300">{s.ema_fast.toFixed(2)}</td>
                          <td className="px-4 py-2 text-right text-slate-300">{s.ema_mid.toFixed(2)}</td>
                          <td className="px-4 py-2 text-center">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${s.wpr > s.ema_fast ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : s.wpr < s.ema_mid ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20' : 'text-slate-500'}`}>
                              {s.wpr > s.ema_fast ? 'BULL' : s.wpr < s.ema_mid ? 'BEAR' : 'MID'}
                            </span>
                          </td>
                        </>
                      )}
                      
                      {selectedStrategy === 'OI_BREAKOUT' && (
                        <>
                          <td className="px-4 py-2 text-right text-slate-500">-</td>
                          <td className="px-4 py-2 text-right text-slate-500">-</td>
                          <td className="px-4 py-2 text-right text-slate-500">-</td>
                          <td className="px-4 py-2 text-center text-slate-500">-</td>
                        </>
                      )}
                      <td className="px-4 py-2 text-center">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          s.signal === 'LONG' ? 'bg-emerald-500/20 text-emerald-400' : 
                          s.signal === 'SHORT' ? 'bg-rose-500/20 text-rose-400' : 'text-slate-500'
                        }`}>
                          {s.signal}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-center text-slate-400">
                        {formatDate(s.last_updated)}
                      </td>
                      <td className="px-4 py-2 text-center">
                        <button 
                          onClick={() => openTradeModal(s.symbol, s.ltp, s.signal === 'SHORT' ? 'SHORT' : 'LONG')}
                          className="bg-indigo-600 hover:bg-indigo-500 text-white text-[10px] px-2 py-1 rounded"
                        >
                          TRADE LIVE
                        </button>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>

      </div>
      
      {showModal && tradeForm && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 max-w-sm w-full shadow-2xl">
            <h3 className="text-xl font-bold text-white mb-1">Live Order: {tradeForm.symbol}</h3>
            <p className="text-sm text-slate-400 mb-4">{tradeForm.trade_type} Order</p>
            
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1">Product Type</label>
                  <select 
                    value={tradeForm.product_type}
                    onChange={(e) => setTradeForm({...tradeForm, product_type: e.target.value})}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:border-indigo-500"
                  >
                    <option value="MIS">MIS (Intraday)</option>
                    <option value="CNC">CNC (Delivery)</option>
                  </select>
                </div>
                <div className="flex items-center mt-6">
                  <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                    <input 
                      type="checkbox"
                      checked={tradeForm.is_amo}
                      onChange={(e) => setTradeForm({...tradeForm, is_amo: e.target.checked})}
                      className="rounded bg-slate-950 border-slate-700 text-indigo-500 focus:ring-indigo-500 h-4 w-4"
                    />
                    After Market (AMO)
                  </label>
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Quantity</label>
                <input 
                  type="number" 
                  value={tradeForm.qty}
                  onChange={(e) => setTradeForm({...tradeForm, qty: e.target.value})}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:border-indigo-500" 
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Limit Price (Entry)</label>
                <input 
                  type="number" step="0.05"
                  value={tradeForm.price}
                  onChange={(e) => setTradeForm({...tradeForm, price: e.target.value})}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:border-indigo-500" 
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1">Stop Loss Price</label>
                  <input 
                    type="number" step="0.05"
                    value={tradeForm.sl}
                    onChange={(e) => {
                      const newSl = parseFloat(e.target.value);
                      setTradeForm({...tradeForm, sl: e.target.value});
                    }}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:border-rose-500" 
                  />
                  <div className="mt-2 flex items-center gap-2">
                    <input 
                      type="number" step="0.1"
                      value={tradeForm.price ? (((parseFloat(tradeForm.sl) - parseFloat(tradeForm.price)) / parseFloat(tradeForm.price)) * 100).toFixed(2) : ''}
                      onChange={(e) => {
                        const pct = parseFloat(e.target.value);
                        if (!isNaN(pct) && tradeForm.price) {
                          const base = parseFloat(tradeForm.price);
                          const newSl = base * (1 + pct / 100);
                          const rt = (price) => Math.round(price / 0.05) * 0.05;
                          setTradeForm({...tradeForm, sl: rt(newSl).toFixed(2)});
                        }
                      }}
                      className="w-20 bg-slate-950 border border-slate-800 rounded px-2 py-1 text-[10px] text-rose-400 focus:border-rose-500"
                    />
                    <span className="text-[10px] text-slate-500">% diff</span>
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1">Target Price</label>
                  <input 
                    type="number" step="0.05"
                    value={tradeForm.tgt}
                    onChange={(e) => {
                      setTradeForm({...tradeForm, tgt: e.target.value});
                    }}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:border-emerald-500" 
                  />
                  <div className="mt-2 flex items-center gap-2">
                    <input 
                      type="number" step="0.1"
                      value={tradeForm.price ? (((parseFloat(tradeForm.tgt) - parseFloat(tradeForm.price)) / parseFloat(tradeForm.price)) * 100).toFixed(2) : ''}
                      onChange={(e) => {
                        const pct = parseFloat(e.target.value);
                        if (!isNaN(pct) && tradeForm.price) {
                          const base = parseFloat(tradeForm.price);
                          const newTgt = base * (1 + pct / 100);
                          const rt = (price) => Math.round(price / 0.05) * 0.05;
                          setTradeForm({...tradeForm, tgt: rt(newTgt).toFixed(2)});
                        }
                      }}
                      className="w-20 bg-slate-950 border border-slate-800 rounded px-2 py-1 text-[10px] text-emerald-400 focus:border-emerald-500"
                    />
                    <span className="text-[10px] text-slate-500">% diff</span>
                  </div>
                </div>
              </div>
              
              {(tradeForm.product_type !== 'MIS' || tradeForm.is_amo) && (
                <div className="text-xs text-amber-400 bg-amber-400/10 border border-amber-400/20 p-2 rounded">
                  Note: SL and Target legs are not supported for CNC or AMO. Only the limit entry order will be placed.
                </div>
              )}
            </div>
            
            <div className="mt-6 flex justify-end gap-3">
              <button 
                onClick={() => setShowModal(false)}
                className="px-4 py-2 rounded-lg text-sm font-medium text-slate-300 hover:bg-slate-800 transition-colors"
              >
                Cancel
              </button>
              <button 
                onClick={submitTrade}
                disabled={loading}
                className="px-4 py-2 rounded-lg text-sm font-bold bg-indigo-600 text-white hover:bg-indigo-500 transition-colors flex items-center gap-2"
              >
                {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                Place Order
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
