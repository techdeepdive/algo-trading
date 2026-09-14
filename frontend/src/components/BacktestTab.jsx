import React, { useState, useEffect } from 'react';
import { Play, Loader2 } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export default function BacktestTab({ credentials }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [results, setResults] = useState(null);
  const [downloads, setDownloads] = useState([]);

  // Form State
  const [formData, setFormData] = useState({
    strategy_name: 'EMA_WPR',
    ema_fast: 5,
    ema_mid: 15,
    ema_slow: 50,
    wpr_period: 70,
    rsi_period: 14,
    bb_period: 20,
    initial_capital: 100000,
    quantity_per_trade: 1,
    csv_filename: '',
    stop_loss_pct: 2.0,
    target_pct: 4.0,
    trailing_stop_pct: 0.0,
    timeframe: 'DAY'
  });

  const [file, setFile] = useState(null);

  useEffect(() => {
    fetch('/downloads')
      .then(res => res.json())
      .then(data => {
        if (data.files) {
          setDownloads(data.files);
        }
      })
      .catch(() => {});
  }, []);

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleFileChange = (e) => {
    if (e.target.files.length > 0) {
      setFile(e.target.files[0]);
      setFormData({ ...formData, csv_filename: '' }); // Clear select if file chosen
    }
  };

  const runBacktest = async () => {
    if (!file && !formData.csv_filename) {
      setError('Please upload a CSV file or select from downloads to run backtest.');
      return;
    }

    setLoading(true);
    setError(null);
    setResults(null);

    const formDataObj = new FormData();
    Object.keys(formData).forEach(key => formDataObj.append(key, formData[key]));
    if (file) {
      formDataObj.append('csv_file', file);
    }

    try {
      const res = await fetch('/backtest', {
        method: 'POST',
        body: formDataObj
      });
      const data = await res.json();
      if (data.status === 'success') {
        setResults(data);
      } else {
        setError(data.message || 'Backtest failed.');
      }
    } catch (e) {
      setError(e.toString());
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl shadow-xl p-5 mb-6">
      <h2 className="text-lg font-semibold text-white mb-5">Backtest Configuration</h2>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-5">
        
        {/* Data Source */}
        <div className="lg:col-span-3 grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
             <label className="block text-xs font-medium text-slate-400 mb-1">Select Downloaded CSV</label>
             <select 
               name="csv_filename" 
               value={formData.csv_filename} 
               onChange={handleChange}
               className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
             >
               <option value="">-- Choose File --</option>
               {downloads.map(d => (
                 <option key={d.filename} value={d.filename}>{d.filename}</option>
               ))}
             </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Or Upload Custom CSV</label>
            <div className="bg-slate-950 border border-slate-800 rounded-lg p-1.5 flex items-center h-[38px]">
              <input type="file" onChange={handleFileChange} className="w-full text-xs text-slate-400 file:mr-3 file:py-1 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-medium file:bg-indigo-600 file:text-white hover:file:bg-indigo-500 file:cursor-pointer" />
            </div>
          </div>
        </div>

        {/* Settings */}
        <div>
           <label className="block text-xs font-medium text-slate-400 mb-1">Strategy</label>
           <select name="strategy_name" value={formData.strategy_name} onChange={handleChange} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none">
             <option value="EMA_CROSS">EMA Crossover (Fast/Mid)</option>
             <option value="EMA_WPR">EMA + Williams %R</option>
             <option value="RSI_MR">RSI Mean Reversion</option>
             <option value="BB_BREAKOUT">Bollinger Bands Breakout</option>
             <option value="OI_BREAKOUT">OI Breakout (Options)</option>
           </select>
        </div>
        {/* Strategy Parameters (Dynamic based on selected strategy) */}
        {formData.strategy_name.includes('EMA') && (
          <>
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">EMA Fast</label>
              <input type="number" name="ema_fast" value={formData.ema_fast} onChange={handleChange} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none" />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">EMA Mid</label>
              <input type="number" name="ema_mid" value={formData.ema_mid} onChange={handleChange} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none" />
            </div>
          </>
        )}
        
        {formData.strategy_name === 'EMA_WPR' && (
          <>
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">EMA Slow</label>
              <input type="number" name="ema_slow" value={formData.ema_slow} onChange={handleChange} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none" />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">WPR Period</label>
              <input type="number" name="wpr_period" value={formData.wpr_period} onChange={handleChange} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none" />
            </div>
          </>
        )}

        {formData.strategy_name === 'RSI_MR' && (
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">RSI Period</label>
            <input type="number" name="rsi_period" value={formData.rsi_period} onChange={handleChange} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none" />
          </div>
        )}

        {formData.strategy_name === 'BB_BREAKOUT' && (
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">BB Period</label>
            <input type="number" name="bb_period" value={formData.bb_period} onChange={handleChange} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none" />
          </div>
        )}
        
        {formData.strategy_name === 'OI_BREAKOUT' && (
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">OI Spike (%)</label>
            <input type="number" name="oi_spike_pct" value={formData.oi_spike_pct || 10} onChange={handleChange} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none" />
          </div>
        )}

        {/* Trade Execution Settings */}
        <div className="lg:col-span-3 border-t border-slate-800 my-2 pt-4">
           <h4 className="text-sm font-semibold text-white mb-3">Execution Settings</h4>
        </div>
        <div>
           <label className="block text-xs font-medium text-slate-400 mb-1">Timeframe</label>
           <select name="timeframe" value={formData.timeframe} onChange={handleChange} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none">
             <option value="1">1 Minute</option>
             <option value="5">5 Minutes</option>
             <option value="15">15 Minutes</option>
             <option value="60">60 Minutes</option>
             <option value="DAY">Daily</option>
           </select>
        </div>
        <div>
           <label className="block text-xs font-medium text-slate-400 mb-1">Total Capital</label>
           <input type="number" name="initial_capital" value={formData.initial_capital} onChange={handleChange} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none" />
        </div>
        <div>
           <label className="block text-xs font-medium text-slate-400 mb-1">Qty per Trade (Lots)</label>
           <input type="number" name="quantity_per_trade" value={formData.quantity_per_trade} onChange={handleChange} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none" />
        </div>

        {/* Trade & Risk Settings */}
        <div className="lg:col-span-3 border-t border-slate-800 my-2 pt-4">
           <h3 className="text-sm font-semibold text-white mb-3">Trade & Risk Settings</h3>
           <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
             <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Stop Loss (%)</label>
                <input type="number" step="0.1" name="stop_loss_pct" value={formData.stop_loss_pct} onChange={handleChange} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none" />
             </div>
             <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Target (%)</label>
                <input type="number" step="0.1" name="target_pct" value={formData.target_pct} onChange={handleChange} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none" />
             </div>
             <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Trailing Stop (%)</label>
                <input type="number" step="0.1" name="trailing_stop_pct" value={formData.trailing_stop_pct} onChange={handleChange} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none" />
             </div>
             <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Slippage (%)</label>
                <input type="number" step="0.01" name="slippage_pct" value={formData.slippage_pct || 0.1} onChange={handleChange} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none" />
             </div>
           </div>
        </div>

      </div>

      <button 
        onClick={runBacktest}
        disabled={loading}
        className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-medium px-6 py-2.5 rounded-lg transition-colors flex items-center justify-center gap-2"
      >
        {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
        <span>Run Backtest</span>
      </button>

      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 mt-6 text-rose-300 text-sm">
          {error}
        </div>
      )}

      {results && results.summary && (
        <div className="mt-6 border-t border-slate-800 pt-6">
          <h3 className="text-lg font-bold text-white mb-4">Results</h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
            <div className="p-4 bg-slate-950 border border-slate-800 rounded-lg">
              <div className="text-xs text-slate-400 mb-1">Total Trades</div>
              <div className="text-xl font-bold text-white">{results.summary.total_trades}</div>
            </div>
            <div className="p-4 bg-slate-950 border border-slate-800 rounded-lg">
              <div className="text-xs text-slate-400 mb-1">Total Return</div>
              <div className={`text-xl font-bold ${results.summary.total_pnl_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {results.summary.total_pnl_pct >= 0 ? '+' : ''}{results.summary.total_pnl_pct.toFixed(2)}%
              </div>
            </div>
            <div className="p-4 bg-slate-950 border border-slate-800 rounded-lg">
              <div className="text-xs text-slate-400 mb-1">Absolute P/L</div>
              <div className={`text-xl font-bold ${(results.summary.final_capital - formData.initial_capital) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                ₹{(results.summary.final_capital - formData.initial_capital).toFixed(2)}
              </div>
            </div>
            <div className="p-4 bg-slate-950 border border-slate-800 rounded-lg">
              <div className="text-xs text-slate-400 mb-1">Win Rate</div>
              <div className="text-xl font-bold text-indigo-400">{results.summary.win_rate.toFixed(2)}%</div>
            </div>
            <div className="p-4 bg-slate-950 border border-slate-800 rounded-lg">
              <div className="text-xs text-slate-400 mb-1">Max Drawdown</div>
              <div className="text-xl font-bold text-rose-400">{results.summary.max_drawdown_pct.toFixed(2)}%</div>
            </div>
          </div>
          
          <div className="mt-4">
             <div className="flex justify-between items-center mb-2">
               <h4 className="text-sm font-bold text-white">Trade Log</h4>
               <span className="text-xs text-slate-400">
                 Symbol: <span className="font-bold text-white">{formData.csv_filename ? formData.csv_filename.split('_')[0] : (file ? file.name.split('_')[0] : 'Custom')}</span>
               </span>
             </div>
             <div className="max-h-[300px] overflow-y-auto bg-slate-950 rounded-lg border border-slate-800">
               <table className="w-full text-left text-xs whitespace-nowrap">
                 <thead className="bg-slate-900 sticky top-0 text-slate-400">
                   <tr>
                     <th className="px-4 py-2">Entry Time</th>
                     <th className="px-4 py-2">Reason</th>
                     <th className="px-4 py-2">Entry Price</th>
                     <th className="px-4 py-2">Exit Time</th>
                     <th className="px-4 py-2">Exit Price</th>
                     <th className="px-4 py-2">Capital Used</th>
                     <th className="px-4 py-2 text-right">PnL %</th>
                     <th className="px-4 py-2 text-right">PnL ₹</th>
                   </tr>
                 </thead>
                 <tbody className="divide-y divide-slate-800">
                   {results.trades.length === 0 ? (
                     <tr><td colSpan="8" className="px-4 py-4 text-center text-slate-500">No trades executed</td></tr>
                   ) : (
                     results.trades.map((t, i) => {
                       const pnlAbs = t.capital_used * (t.pnl_pct / 100);
                       return (
                         <tr key={i}>
                           <td className="px-4 py-2">{t.entry_date}</td>
                           <td className="px-4 py-2 text-indigo-400 font-bold">{t.exit_reason}</td>
                           <td className="px-4 py-2">₹{t.entry_price.toFixed(2)}</td>
                           <td className="px-4 py-2">{t.exit_date}</td>
                           <td className="px-4 py-2">₹{t.exit_price.toFixed(2)}</td>
                           <td className="px-4 py-2">₹{t.capital_used.toFixed(2)}</td>
                           <td className={`px-4 py-2 text-right font-bold ${t.pnl_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                             {t.pnl_pct >= 0 ? '+' : ''}{t.pnl_pct.toFixed(2)}%
                           </td>
                           <td className={`px-4 py-2 text-right font-bold ${pnlAbs >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                             {pnlAbs >= 0 ? '+' : ''}₹{pnlAbs.toFixed(2)}
                           </td>
                         </tr>
                       );
                     })
                   )}
                 </tbody>
               </table>
             </div>
          </div>

          {results.equity_curve && results.equity_curve.length > 0 && (
            <div className="mt-8">
               <h4 className="text-sm font-bold text-white mb-4">Equity Curve (Total Return %)</h4>
               <div className="bg-slate-950 rounded-lg border border-slate-800 p-4 h-64">
                 <ResponsiveContainer width="100%" height="100%">
                   <LineChart data={results.equity_curve.map((val, i) => {
                       let label = `Trade ${i}`;
                       if (i > 0 && results.trades[i - 1]) {
                           label = results.trades[i - 1].exit_date;
                       } else if (i === 0) {
                           label = "Start";
                       }
                       return { step: label, return: val };
                   })}>
                     <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                     <XAxis 
                       dataKey="step" 
                       tick={{ fill: '#64748b', fontSize: 10 }} 
                       axisLine={false} 
                       tickMargin={10}
                       minTickGap={30}
                     />
                     <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} axisLine={false} tickLine={false} tickFormatter={val => `${val}%`} />
                     <Tooltip
                       contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', color: '#f8fafc', borderRadius: '0.5rem' }}
                       itemStyle={{ color: '#818cf8', fontWeight: 'bold' }}
                       formatter={val => [`${val}%`, 'Total Return']}
                       labelFormatter={label => `Time: ${label}`}
                     />
                     <Line type="monotone" dataKey="return" stroke="#818cf8" strokeWidth={2} dot={false} activeDot={{ r: 4, fill: '#818cf8', stroke: '#312e81' }} />
                   </LineChart>
                 </ResponsiveContainer>
               </div>
            </div>
          )}

        </div>
      )}
    </div>
  );
}
