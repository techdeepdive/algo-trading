import React, { useState } from 'react';
import { Loader2, TrendingUp, Play, LineChart, ShieldCheck, Activity, Download } from 'lucide-react';
import {
  AreaChart as RechartsAreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine
} from 'recharts';

const STRATEGY_LEGS = {
  "Long Straddle": 2, "Short Straddle": 2, 
  "Long Strangle": 2, "Short Strangle": 2,
  "Long Iron Condor": 4, "Short Iron Condor": 4,
  "Long Butterfly (Call)": 3,
  "Bull Call Spread": 2, "Bear Put Spread": 2
};
const STRATEGIES = Object.keys(STRATEGY_LEGS);

const ASSETS = [
  { symbol: "NIFTY", exchange: "INDEX" },
  { symbol: "BANKNIFTY", exchange: "INDEX" },
  { symbol: "SENSEX", exchange: "INDEX" },
  { symbol: "GOLD", exchange: "MCX" },
  { symbol: "SILVER", exchange: "MCX" },
  { symbol: "CRUDEOIL", exchange: "MCX" }
];

export default function HedgingTab({ credentials }) {
  const [asset, setAsset] = useState(ASSETS[0].symbol);
  const [strategy, setStrategy] = useState(STRATEGIES[0]);
  const [expiryFlag, setExpiryFlag] = useState('WEEK');
  const [slippage, setSlippage] = useState('0.1');

  const today = new Date().toISOString().split('T')[0];
  const lastWeek = new Date(new Date().setDate(new Date().getDate() - 7)).toISOString().split('T')[0];
  
  const [fromDate, setFromDate] = useState(lastWeek);
  const [toDate, setToDate] = useState(today);
  const [timeframe, setTimeframe] = useState('15');
  const [csvFile, setCsvFile] = useState(null);
  const [legFiles, setLegFiles] = useState({});
  const [capital, setCapital] = useState(100000);
  const [qtyMultiplier, setQtyMultiplier] = useState(1);
  const [slPct, setSlPct] = useState('');
  const [tpPct, setTpPct] = useState('');

  const [loadingSim, setLoadingSim] = useState(false);
  const [loadingBacktest, setLoadingBacktest] = useState(false);
  const [loadingDownload, setLoadingDownload] = useState(false);
  
  const [simResult, setSimResult] = useState(null);
  const [backtestResult, setBacktestResult] = useState(null);
  const [error, setError] = useState('');

  const getExchange = (sym) => ASSETS.find(a => a.symbol === sym)?.exchange || "INDEX";

  const downloadLegCsvs = async () => {
    if (!credentials.client_id || !credentials.access_token) {
      setError("Please fill in Dhan credentials on the Home tab first.");
      return;
    }

    setLoadingDownload(true);
    setError(null);
    const numLegs = STRATEGY_LEGS[strategy];

    try {
      for (let i = 0; i < numLegs; i++) {
        const res = await fetch('/download_leg_csv', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ...credentials,
            symbol: asset,
            exchange: getExchange(asset),
            strategy,
            leg_index: i,
            expiry_flag: expiryFlag,
            from_date: fromDate,
            to_date: toDate,
            timeframe,
            slippage: parseFloat(slippage),
            capital: parseFloat(capital),
            qty_multiplier: parseInt(qtyMultiplier),
            sl_pct: parseFloat(slPct || 0),
            tp_pct: parseFloat(tpPct || 0)
          })
        });

        if (!res.ok) {
          const text = await res.text();
          throw new Error(text || `Failed to download Leg ${i + 1}`);
        }

        // Trigger browser download
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        // Extract filename from header if present
        const disposition = res.headers.get('content-disposition');
        let filename = `leg${i+1}.csv`;
        if (disposition && disposition.indexOf('filename=') !== -1) {
          filename = disposition.split('filename=')[1];
        }
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        
        // Brief pause between downloads to prevent browser blocking
        await new Promise(r => setTimeout(r, 500));
      }
    } catch (err) {
      setError(err.message || "Error generating CSVs");
    } finally {
      setLoadingDownload(false);
    }
  };

  const runSimulation = async () => {
    if (!credentials.client_id || !credentials.access_token) {
      setError('Client ID and Access Token required.');
      return;
    }
    
    setLoadingSim(true);
    setError('');
    setSimResult(null);

    try {
      const res = await fetch('/simulate_hedging', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...credentials,
          symbol: asset,
          exchange: getExchange(asset),
          strategy
        })
      });
      
      const data = await res.json();
      if (data.status === 'success') {
        setSimResult(data.data);
      } else {
        setError(data.message);
      }
    } catch (e) {
      setError("Network error or server unreachable.");
    } finally {
      setLoadingSim(false);
    }
  };

  const runBacktest = async () => {
    if (!credentials.client_id || !credentials.access_token) {
      setError('Client ID and Access Token required.');
      return;
    }

    setLoadingBacktest(true);
    setError('');
    setBacktestResult(null);

    try {
      let res;
      // Check if they uploaded individual legs
      const numLegs = STRATEGY_LEGS[strategy];
      const hasAllLegs = Array.from({length: numLegs}).every((_, i) => legFiles[`leg${i+1}`]);

      if (hasAllLegs) {
        const formData = new FormData();
        for (let i = 1; i <= numLegs; i++) {
          formData.append(`file_leg${i}`, legFiles[`leg${i}`]);
        }
        formData.append('strategy', strategy);
        formData.append('slippage', slippage);
        formData.append('capital', capital);
        formData.append('qty_multiplier', qtyMultiplier);
        formData.append('sl_pct', slPct || 0);
        formData.append('tp_pct', tpPct || 0);

        res = await fetch('/backtest_hedging', {
          method: 'POST',
          body: formData
        });
      } else if (csvFile) {
        const formData = new FormData();
        formData.append('csv_file', csvFile);
        formData.append('strategy', strategy);
        formData.append('slippage', slippage);
        formData.append('capital', capital);
        formData.append('qty_multiplier', qtyMultiplier);
        formData.append('sl_pct', slPct || 0);
        formData.append('tp_pct', tpPct || 0);

        res = await fetch('/backtest_hedging', {
          method: 'POST',
          body: formData
        });
      } else {
        res = await fetch('/backtest_hedging', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ...credentials,
            symbol: asset,
            exchange: getExchange(asset),
            strategy,
            expiry_flag: expiryFlag,
            from_date: fromDate,
            to_date: toDate,
            timeframe,
            slippage: parseFloat(slippage),
            capital: parseFloat(capital),
            qty_multiplier: parseInt(qtyMultiplier),
            sl_pct: parseFloat(slPct || 0),
            tp_pct: parseFloat(tpPct || 0)
          })
        });
      }
      
      const data = await res.json();
      if (data.status === 'success') {
        setBacktestResult(data.data);
      } else {
        setError(data.message);
      }
    } catch (e) {
      setError("Network error or server unreachable.");
    } finally {
      setLoadingBacktest(false);
    }
  };

  return (
    <div className="space-y-6">
      
      {/* Input Configuration Panel */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl">
        <h2 className="text-lg font-semibold text-white mb-5 flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-indigo-400" />
          Options Hedging & Multi-Leg Strategies
        </h2>
        
        {error && (
          <div className="p-4 mb-5 bg-rose-500/10 border border-rose-500/40 rounded-lg text-rose-200 text-sm">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Asset *</label>
            <select value={asset} onChange={e => setAsset(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-white focus:ring-1 focus:ring-indigo-500">
              {ASSETS.map(a => <option key={a.symbol} value={a.symbol}>{a.symbol} ({a.exchange})</option>)}
            </select>
          </div>
          
          <div className="lg:col-span-2">
            <label className="block text-xs font-medium text-slate-400 mb-1">Strategy Profile *</label>
            <select value={strategy} onChange={e => setStrategy(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-white focus:ring-1 focus:ring-indigo-500">
              {STRATEGIES.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Expiry Type</label>
            <select value={expiryFlag} onChange={e => setExpiryFlag(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-white focus:ring-1 focus:ring-indigo-500">
              <option value="WEEK">Weekly</option>
              <option value="MONTH">Monthly</option>
            </select>
          </div>
          
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">From Date (Backtest)</label>
            <input type="date" value={fromDate} onChange={e => setFromDate(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-white" />
          </div>
          
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">To Date (Backtest)</label>
            <input type="date" value={toDate} onChange={e => setToDate(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-white" />
          </div>
          
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Timeframe</label>
            <select value={timeframe} onChange={e => setTimeframe(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-indigo-500 transition-colors">
              <option value="1">1 Minute</option>
              <option value="5">5 Minutes</option>
              <option value="15">15 Minutes</option>
              <option value="60">1 Hour</option>
              <option value="DAY">1 Day</option>
            </select>
          </div>
          
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Slippage (%)</label>
            <input type="number" step="0.1" value={slippage} onChange={e => setSlippage(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-white" />
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-5">
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Total Capital (₹)</label>
            <input type="number" step="1000" value={capital} onChange={e => setCapital(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-white" />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Lot Multiplier</label>
            <input type="number" step="1" min="1" value={qtyMultiplier} onChange={e => setQtyMultiplier(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-white" />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Stop Loss % (Optional)</label>
            <input type="number" step="0.5" placeholder="e.g. 5" value={slPct} onChange={e => setSlPct(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-white" />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Target Profit % (Optional)</label>
            <input type="number" step="0.5" placeholder="e.g. 10" value={tpPct} onChange={e => setTpPct(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-white" />
          </div>
        </div>

        <div className="lg:col-span-4 bg-slate-950/50 p-4 rounded-lg border border-slate-800 mb-5">
          <h4 className="text-sm font-semibold text-slate-300 mb-3">Offline Backtesting (Upload CSVs)</h4>
          <p className="text-xs text-slate-500 mb-4">Upload the CSV data downloaded from the Historical tab for each leg to bypass API rate limits.</p>
          
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {Array.from({ length: STRATEGY_LEGS[strategy] }).map((_, i) => (
              <div key={i}>
                <label className="block text-xs font-medium text-slate-400 mb-1">Leg {i + 1} CSV</label>
                <input 
                  type="file" 
                  accept=".csv" 
                  onChange={e => setLegFiles({...legFiles, [`leg${i+1}`]: e.target.files[0]})} 
                  className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2 py-1.5 text-xs text-white file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-xs file:font-medium file:bg-indigo-600 file:text-white hover:file:bg-indigo-500" 
                />
              </div>
            ))}
          </div>
          
          <div className="mt-4 pt-4 border-t border-slate-800/50">
            <label className="block text-xs font-medium text-slate-400 mb-1">OR Upload Single Master CSV</label>
            <input 
              type="file" 
              accept=".csv" 
              onChange={e => setCsvFile(e.target.files[0])} 
              className="w-full max-w-sm bg-slate-900 border border-slate-800 rounded-lg px-2 py-1.5 text-xs text-white file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-xs file:font-medium file:bg-slate-700 file:text-white hover:file:bg-slate-600" 
            />
          </div>
        </div>

        <div className="flex gap-4">
          <button 
            onClick={runSimulation}
            disabled={loadingSim || loadingBacktest}
            className="flex-1 bg-indigo-600/20 text-indigo-400 border border-indigo-500/30 hover:bg-indigo-600/30 font-medium rounded-lg px-4 py-3 flex justify-center items-center gap-2 transition-colors"
          >
            {loadingSim ? <Loader2 className="w-5 h-5 animate-spin" /> : <LineChart className="w-5 h-5" />}
            Live Payoff Simulator (Current Expiry)
          </button>
          
          <button
            onClick={downloadLegCsvs}
            disabled={loadingDownload}
            className="flex-1 flex items-center justify-center gap-2 bg-slate-800 hover:bg-slate-700 text-white py-3 rounded-xl font-medium transition-colors disabled:opacity-50 border border-slate-700"
          >
            {loadingDownload ? <div className="animate-spin h-5 w-5 border-2 border-white/20 border-t-white rounded-full"></div> : <Download className="w-5 h-5" />}
            {loadingDownload ? 'Generating...' : 'Download Leg CSVs'}
          </button>
          
          <button 
            onClick={runBacktest}
            disabled={loadingSim || loadingBacktest}
            className="flex-[2] bg-emerald-600/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-600/30 font-medium rounded-lg px-4 py-3 flex justify-center items-center gap-2 transition-colors"
          >
            {loadingBacktest ? <Loader2 className="w-5 h-5 animate-spin" /> : <Play className="w-5 h-5" />}
            Run Historical Backtest
          </button>
        </div>
      </div>

      {/* Simulator Results */}
      {simResult && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl">
          <div className="flex justify-between items-end mb-6">
            <div>
              <h3 className="text-lg font-bold text-white mb-1">Payoff Simulation</h3>
              <p className="text-xs text-slate-400">ATM Strike: <span className="text-white font-mono">{simResult.atm}</span></p>
            </div>
            <div className="flex gap-4 text-sm">
              <div className="bg-slate-950 px-3 py-2 rounded-lg border border-slate-800 text-center">
                <span className="block text-xs text-slate-500 mb-1">Max Profit</span>
                <span className="font-bold text-emerald-400">₹{simResult.max_profit > 900000 ? "Unlimited" : simResult.max_profit}</span>
              </div>
              <div className="bg-slate-950 px-3 py-2 rounded-lg border border-slate-800 text-center">
                <span className="block text-xs text-slate-500 mb-1">Max Loss</span>
                <span className="font-bold text-rose-400">₹{simResult.max_loss < -900000 ? "Unlimited" : simResult.max_loss}</span>
              </div>
              <div className="bg-slate-950 px-3 py-2 rounded-lg border border-slate-800 text-center">
                <span className="block text-xs text-slate-500 mb-1">Net Premium</span>
                <span className={`font-bold ${simResult.net_premium >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  ₹{simResult.net_premium}
                </span>
              </div>
            </div>
          </div>

          <div className="h-64 mb-6">
            <ResponsiveContainer width="100%" height="100%">
              <RechartsLineChart data={simResult.payoff_curve}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis dataKey="underlying_price" tick={{fill: '#64748b', fontSize: 10}} axisLine={false} tickMargin={10} domain={['dataMin', 'dataMax']} type="number" />
                <YAxis tick={{fill: '#94a3b8', fontSize: 12}} axisLine={false} tickLine={false} />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', color: '#f8fafc', borderRadius: '0.5rem' }}
                  formatter={(value) => [`₹${value}`, 'Projected PNL']}
                  labelFormatter={(val) => `Underlying: ₹${val}`}
                />
                <ReferenceLine y={0} stroke="#475569" strokeDasharray="3 3" />
                <ReferenceLine x={simResult.atm} stroke="#818cf8" strokeDasharray="3 3" label={{ position: 'top', value: 'ATM', fill: '#818cf8', fontSize: 10 }} />
                <Line type="monotone" dataKey="pnl" stroke="#10b981" strokeWidth={2} dot={false} activeDot={{ r: 4, fill: '#10b981' }} />
              </RechartsLineChart>
            </ResponsiveContainer>
          </div>

          <div>
            <h4 className="text-sm font-semibold text-slate-300 mb-3">Legs Setup</h4>
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="text-xs text-slate-400 bg-slate-950/50 border-y border-slate-800">
                  <tr>
                    <th className="px-4 py-2">Action</th>
                    <th className="px-4 py-2">Type</th>
                    <th className="px-4 py-2">Strike</th>
                    <th className="px-4 py-2">Qty</th>
                    <th className="px-4 py-2 text-right">LTP Premium</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/50">
                  {simResult.positions.map((p, i) => (
                    <tr key={i} className="hover:bg-slate-800/20">
                      <td className={`px-4 py-2 font-bold ${p.action === 'BUY' ? 'text-indigo-400' : 'text-rose-400'}`}>{p.action}</td>
                      <td className="px-4 py-2">{p.type}</td>
                      <td className="px-4 py-2 font-mono">{p.strike}</td>
                      <td className="px-4 py-2">{p.qty}</td>
                      <td className="px-4 py-2 text-right font-mono text-slate-300">₹{p.price}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Backtest Results */}
      {backtestResult && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl">
          <div className="flex justify-between items-end mb-6">
            <div>
              <h3 className="text-lg font-bold text-white mb-1">Backtest Report</h3>
              <p className="text-xs text-slate-400">{backtestResult.entry_time} to {backtestResult.exit_time}</p>
            </div>
            <div className="bg-slate-950 px-4 py-2 rounded-lg border border-slate-800 flex items-center gap-4">
              <div className="text-right">
                <div className="text-xs text-slate-500 mb-1">Total Net PNL (inc. slippage)</div>
                <div className={`text-2xl font-bold ${backtestResult.total_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {backtestResult.total_pnl > 0 ? '+' : ''}₹{backtestResult.total_pnl}
                </div>
              </div>
            </div>
          </div>

          {backtestResult.metrics && (
            <div className="grid grid-cols-4 gap-4 mb-6 mt-4 p-4 bg-slate-950 rounded-lg border border-slate-800">
              <div>
                <div className="text-xs text-slate-500">Initial Capital</div>
                <div className="text-sm font-semibold text-white">₹{backtestResult.metrics.initial_capital}</div>
              </div>
              <div>
                <div className="text-xs text-slate-500">Final Capital</div>
                <div className={`text-sm font-semibold ${backtestResult.metrics.final_capital >= backtestResult.metrics.initial_capital ? 'text-emerald-400' : 'text-rose-400'}`}>
                  ₹{backtestResult.metrics.final_capital}
                </div>
              </div>
              <div>
                <div className="text-xs text-slate-500">Max Drawdown</div>
                <div className="text-sm font-semibold text-rose-400">-{backtestResult.metrics.max_drawdown_pct}%</div>
              </div>
              <div>
                <div className="text-xs text-slate-500">Total Trades</div>
                <div className="text-sm font-semibold text-indigo-400">{backtestResult.metrics.total_trades}</div>
              </div>
            </div>
          )}

          <div className="mb-6">
            <h4 className="text-sm font-semibold text-white mb-4">Strategy Equity Curve</h4>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <RechartsAreaChart data={backtestResult.equity_curve}>
                  <defs>
                    <linearGradient id="colorReturn" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#38bdf8" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                  <XAxis dataKey="step" tick={{fill: '#64748b', fontSize: 10}} axisLine={false} tickMargin={10} minTickGap={30} />
                  <YAxis tick={{fill: '#94a3b8', fontSize: 12}} axisLine={false} tickLine={false} />
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', color: '#f8fafc', borderRadius: '0.5rem' }}
                    formatter={(value) => [`₹${value}`, 'Net PNL']}
                    labelFormatter={(val) => `Time: ${val}`}
                  />
                  <ReferenceLine y={0} stroke="#475569" strokeDasharray="3 3" />
                  <Area type="monotone" dataKey="return" stroke="#38bdf8" fillOpacity={1} fill="url(#colorReturn)" strokeWidth={2} activeDot={{ r: 4, fill: '#38bdf8' }} />
                </RechartsAreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div>
            <h4 className="text-sm font-semibold text-white mb-4">Detailed Leg Execution</h4>
            <div className="bg-slate-950 rounded-lg border border-slate-800 overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="text-xs text-slate-400 bg-slate-950/50 border-b border-slate-800">
                  <tr>
                    <th className="px-4 py-3">Action</th>
                    <th className="px-4 py-3">Type</th>
                    <th className="px-4 py-3">Strike</th>
                    <th className="px-4 py-3 text-right">Underlying</th>
                    <th className="px-4 py-3 text-right">IV (%)</th>
                    <th className="px-4 py-3 text-right">Entry</th>
                    <th className="px-4 py-3 text-right">Exit</th>
                    <th className="px-4 py-3 text-right">Qty</th>
                    <th className="px-4 py-3 text-right">Capital Used ₹</th>
                    <th className="px-4 py-3 text-right">Leg PNL</th>
                  </tr>
                </thead>
                <tbody>
                  {backtestResult.legs.map((leg, i) => (
                    <tr key={i} className="border-b border-slate-800/50 hover:bg-slate-800/20">
                      <td className={`px-4 py-3 font-medium ${leg.action === 'BUY' ? 'text-indigo-400' : 'text-rose-400'}`}>{leg.action}</td>
                      <td className="px-4 py-3 text-slate-300">{leg.type}</td>
                      <td className="px-4 py-3 text-slate-300">{leg.strike_val || leg.strike_str}</td>
                      <td className="px-4 py-3 text-right text-slate-300">{leg.spot_entry ? leg.spot_entry : '-'}</td>
                      <td className="px-4 py-3 text-right text-slate-300">{leg.iv ? leg.iv : '-'}</td>
                      <td className="px-4 py-3 text-right">
                        <div className="text-slate-300 font-medium">₹{leg.entry_price || '-'}</div>
                        <div className="text-xs text-slate-500">{leg.entry_time}</div>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="text-slate-300 font-medium">₹{leg.exit_price || '-'}</div>
                        <div className="text-xs text-slate-500">{leg.exit_time}</div>
                      </td>
                      <td className="px-4 py-3 text-right text-slate-300">{leg.qty}</td>
                      <td className="px-4 py-3 text-right text-slate-300">{leg.capital_used ? `₹${leg.capital_used}` : '-'}</td>
                      <td className={`px-4 py-3 text-right font-medium ${leg.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {leg.pnl ? (leg.pnl > 0 ? '+' : '') + leg.pnl : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
