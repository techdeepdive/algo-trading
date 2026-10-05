import React, { useState } from 'react';
import { Play, Loader2 } from 'lucide-react';

const STRATEGY_DESC = {
  "WPR_CROSS_EMA": "Williams %R Cross EMA: Identifies momentum reversals. Bullish when WPR is oversold (<-70) and 5 EMA crosses above 15 EMA.",
  "RSI_MR": "RSI Mean Reversion: Looks for extreme overbought/oversold conditions on the 14-period RSI to predict a snap-back.",
  "BB_BREAKOUT": "Bollinger Band Breakout: Triggers when the price breaks outside the 2 standard deviation Bollinger Bands, indicating strong momentum.",
  "OI_BREAKOUT": "Open Interest Breakout: Not available for standard historical equity data."
};

export default function ScreenerTab({ credentials }) {
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState([]);
  const [error, setError] = useState(null);
  const [selectedStrategy, setSelectedStrategy] = useState('WPR_CROSS_EMA');
  const [watchlists, setWatchlists] = useState(['nifty50']);
  const [customSymbols, setCustomSymbols] = useState('');
  
  // Modal State
  const [showModal, setShowModal] = useState(false);
  const [tradeForm, setTradeForm] = useState(null);

  const runScreener = async () => {
    if (!credentials.client_id || !credentials.access_token) {
      setError("Please save Dhan credentials in the Setup tab first.");
      return;
    }

    setLoading(true);
    setError(null);
    setResults([]);
    try {
      const res = await fetch('/api/algolab/screen', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: credentials.client_id,
          access_token: credentials.access_token,
          strategy_name: selectedStrategy,
          watchlists: watchlists,
          custom_symbols: customSymbols
        })
      });
      const data = await res.json();
      if (data.status === 'success') {
        setResults(data.data || []);
      } else {
        setError(data.message);
      }
    } catch (err) {
      setError(err.toString());
    } finally {
      setLoading(false);
    }
  };

  const toggleWatchlist = (list) => {
    if (watchlists.includes(list)) {
      setWatchlists(watchlists.filter(l => l !== list));
    } else {
      setWatchlists([...watchlists, list]);
    }
  };

  const openTradeModal = (symbol, ltp, trade_type) => {
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
    if (!credentials.client_id || !credentials.access_token) {
      setError("Please save Dhan credentials in the Setup tab first.");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch('/api/algolab/trade', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: credentials.client_id,
          access_token: credentials.access_token,
          ...tradeForm
        })
      });
      const data = await res.json();
      if (data.status === 'success') {
        setShowModal(false);
        alert(`Order Placed: ${data.order_id}`);
      } else {
        alert(`Trade failed: ${data.message}`);
      }
    } catch (err) {
      alert("Error: " + err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
        <h2 className="text-xl font-bold text-white mb-6">On-Demand Screener</h2>
        
        {error && (
          <div className="mb-6 p-4 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm">
            {error}
          </div>
        )}

        {/* Controls */}
        <div className="flex flex-wrap items-center gap-4 mb-4">
          <select 
            value={selectedStrategy}
            onChange={(e) => setSelectedStrategy(e.target.value)}
            className="bg-slate-950 border border-slate-800 rounded-lg px-4 py-2 text-sm text-white"
          >
            <option value="WPR_CROSS_EMA">WPR + 5/15 EMA Crossover</option>
            <option value="RSI_MR">RSI Mean Reversion (14)</option>
            <option value="BB_BREAKOUT">Bollinger Bands Breakout (20,2)</option>
          </select>
          
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input type="checkbox" checked={watchlists.includes('nifty50')} onChange={() => toggleWatchlist('nifty50')} className="rounded bg-slate-950 border-slate-700 text-indigo-500" />
            Nifty 50
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input type="checkbox" checked={watchlists.includes('banknifty')} onChange={() => toggleWatchlist('banknifty')} className="rounded bg-slate-950 border-slate-700 text-indigo-500" />
            BankNifty
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input type="checkbox" checked={watchlists.includes('mcx')} onChange={() => toggleWatchlist('mcx')} className="rounded bg-slate-950 border-slate-700 text-indigo-500" />
            MCX Futures
          </label>
          
          <input 
            type="text"
            placeholder="Custom (e.g. TCS, INFY)"
            value={customSymbols}
            onChange={(e) => setCustomSymbols(e.target.value)}
            className="bg-slate-950 border border-slate-800 rounded-lg px-4 py-2 text-sm text-white w-48"
          />

          <button 
            onClick={runScreener}
            disabled={loading}
            className="ml-auto bg-emerald-600/10 text-emerald-500 border border-emerald-600/20 hover:bg-emerald-600 hover:text-white px-6 py-2 rounded-lg text-sm font-bold transition-all flex items-center gap-2"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            Run Screener
          </button>
        </div>
        
        <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 mb-6">
          <p className="text-sm text-slate-400">
            <strong className="text-white">{selectedStrategy}:</strong> {STRATEGY_DESC[selectedStrategy]}
          </p>
        </div>

        {/* Results Table */}
        <div className="bg-slate-950 border border-slate-800 rounded-xl overflow-hidden mt-6">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-slate-400 uppercase bg-slate-900/50">
              <tr>
                <th className="px-4 py-3">Symbol</th>
                <th className="px-4 py-3">LTP</th>
                <th className="px-4 py-3 text-center">Trend (Fast / Mid)</th>
                <th className="px-4 py-3 text-center">WPR / Ind</th>
                <th className="px-4 py-3 text-center">Signal</th>
                <th className="px-4 py-3 text-center">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {results.length === 0 ? (
                <tr>
                  <td colSpan="6" className="px-4 py-8 text-center text-slate-500">
                    {loading ? "Scanning in progress..." : "No results yet. Click Run Screener."}
                  </td>
                </tr>
              ) : (
                results.map((s, idx) => {
                  const isLong = s.signal === 'LONG';
                  const isShort = s.signal === 'SHORT';
                  
                  return (
                    <tr key={idx} className="hover:bg-slate-900/50 transition-colors">
                      <td className="px-4 py-3 font-medium text-slate-300">{s.symbol}</td>
                      <td className="px-4 py-3 text-white">₹{s.ltp.toFixed(2)}</td>
                      <td className="px-4 py-3 text-center text-xs">
                        <span className={s.ema_fast > s.ema_mid ? "text-emerald-400" : "text-rose-400"}>
                          {s.ema_fast > s.ema_mid ? "FAST > MID" : "FAST < MID"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center text-slate-300">
                        {s.wpr.toFixed(2)}
                      </td>
                      <td className="px-4 py-3 text-center font-bold">
                        <span className={isLong ? "text-emerald-500" : isShort ? "text-rose-500" : "text-slate-600"}>
                          {s.signal}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center">
                        <button 
                          onClick={() => openTradeModal(s.symbol, s.ltp, isShort ? 'SHORT' : 'LONG')}
                          className="bg-indigo-600 hover:bg-indigo-500 text-white text-[10px] px-3 py-1.5 rounded font-medium transition-colors"
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

      {/* Trade Modal */}
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
                    onChange={(e) => setTradeForm({...tradeForm, sl: e.target.value})}
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
                    onChange={(e) => setTradeForm({...tradeForm, tgt: e.target.value})}
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
