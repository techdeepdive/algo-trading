import React, { useState } from 'react';
import { Download, Loader2, Info } from 'lucide-react';

export default function HistoricalTab({ credentials }) {
  const [assetType, setAssetType] = useState('equity'); // 'equity' | 'options'
  const [symbol, setSymbol] = useState('');
  const [exchange, setExchange] = useState('AUTO');
  
  // Options specific state
  const [optionType, setOptionType] = useState('CALL');
  const [expiryFlag, setExpiryFlag] = useState('WEEK');
  const [expiryCode, setExpiryCode] = useState('1');
  const [strike, setStrike] = useState('ATM');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  
  const today = new Date().toISOString().split('T')[0];
  const lastYear = new Date(new Date().setFullYear(new Date().getFullYear() - 1)).toISOString().split('T')[0];
  
  const [fromDate, setFromDate] = useState(lastYear);
  const [toDate, setToDate] = useState(today);
  const [timeframe, setTimeframe] = useState('DAY');

  const [symbolsList, setSymbolsList] = useState([]);

  React.useEffect(() => {
    if (assetType === 'equity' && symbol.length > 0) {
      const timer = setTimeout(() => {
        fetch(`/symbols?q=${symbol}`)
          .then(res => res.json())
          .then(data => setSymbolsList(data.symbols || []))
          .catch(() => {});
      }, 300);
      return () => clearTimeout(timer);
    } else {
      setSymbolsList([]);
    }
  }, [symbol, assetType]);

  const downloadHistorical = async () => {
    if (!credentials.client_id || !credentials.access_token) {
      setError('Client ID and Access Token are required.');
      return;
    }
    if (!symbol) {
      setError('Please enter a symbol.');
      return;
    }
    
    setLoading(true);
    setError('');
    setSuccess('');
    
    try {
      const res = await fetch('/historical', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...credentials,
          asset_type: assetType,
          symbol: assetType === 'options' ? symbol.toUpperCase() : symbol,
          from_date: fromDate,
          to_date: toDate,
          timeframe,
          exchange: exchange === 'AUTO' ? undefined : exchange,
          option_type: optionType,
          expiry_flag: expiryFlag,
          expiry_code: expiryCode,
          strike: strike
        })
      });
      const data = await res.json();
      if (data.status === 'error') {
        setError(data.message);
      } else {
        setSuccess(`Downloaded ${data.rows} rows.`);
        
        // Trigger local browser download for each generated file
        const filenames = data.filename.split(', ');
        filenames.forEach(file => {
          const a = document.createElement('a');
          a.href = `/downloads/${encodeURIComponent(file)}`;
          a.download = file;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
        });
      }
    } catch (e) {
      setError('Network error or server unreachable.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl shadow-xl p-5 mb-6">
      <div className="flex justify-between items-center mb-5">
         <h2 className="text-lg font-semibold text-white">Download Historical Data</h2>
         
         {/* Asset Type Toggle */}
         <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800 self-start mb-2">
          <button
            onClick={() => setAssetType('equity')}
            className={`px-4 py-1.5 text-xs font-medium rounded-md transition-colors ${assetType === 'equity' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'}`}
          >
            Equity / Futures
          </button>
           <button 
             onClick={() => setAssetType('options')}
             className={`px-4 py-1.5 text-xs font-bold rounded-md transition-colors ${assetType === 'options' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'}`}
           >
             Options
           </button>
         </div>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
        
        {assetType === 'equity' ? (
          <>
            <div className="lg:col-span-2">
                <label className="block text-xs font-medium text-slate-400 mb-1">Stock / Future Symbol *</label>
                <input 
                  type="text" 
                  list="symbols_list"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500" 
                  placeholder="e.g. RELIANCE, NIFTY, CRUDEOIL, GOLD" 
                />
                <datalist id="symbols_list">
                  {symbolsList.map((s, i) => (
                    <option key={i} value={s.symbol}>{s.exchange}</option>
                  ))}
                </datalist>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">Exchange *</label>
              <select
                value={exchange}
                onChange={(e) => setExchange(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              >
                <option value="AUTO">Auto Detect</option>
                <option value="NSE">NSE (Stocks)</option>
                <option value="BSE">BSE (Stocks)</option>
                <option value="MCX">MCX (Commodities)</option>
                <option value="INDEX">INDEX (Nifty/Sensex)</option>
              </select>
            </div>
          </>
        ) : (
          <>
            <div className="lg:col-span-1">
              <label className="block text-xs font-medium text-slate-400 mb-1">Underlying Index *</label>
              <input 
                type="text" 
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500" 
                placeholder="e.g. NIFTY, BANKNIFTY" 
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">Option Type</label>
              <select value={optionType} onChange={e => setOptionType(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none">
                <option value="CALL">CALL</option>
                <option value="PUT">PUT</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">Strike Range</label>
              <select value={strike} onChange={e => setStrike(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none">
                <option value="ATM">ATM Only</option>
                <option value="ATM_1">ATM-1 to ATM+1</option>
                <option value="ATM_2">ATM-2 to ATM+2</option>
                <option value="ATM_3">ATM-3 to ATM+3</option>
                <option value="ATM_5">ATM-5 to ATM+5</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">Expiry Code</label>
              <select value={expiryCode} onChange={e => setExpiryCode(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none">
                <option value="1">1 (Near)</option>
                <option value="2">2 (Next)</option>
                <option value="3">3 (Far)</option>
              </select>
            </div>
          </>
        )}

        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1">From Date</label>
          <input 
            type="date" 
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500" 
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1">To Date</label>
          <input 
            type="date" 
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500" 
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1">Timeframe</label>
          <select 
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
          >
            <option value="1">1 Minute</option>
            <option value="5">5 Minutes</option>
            <option value="15">15 Minutes</option>
            <option value="60">60 Minutes</option>
            {assetType === 'equity' && <option value="DAY">Daily</option>}
          </select>
        </div>
        <div className="flex items-end lg:col-span-1">
          <button 
            onClick={downloadHistorical}
            disabled={loading}
            className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2.5 rounded-lg transition-colors flex items-center justify-center gap-2"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
            <span>Download CSV(s)</span>
          </button>
        </div>
      </div>

      {assetType === 'options' && (
        <div className="flex items-start gap-2 bg-slate-950 border border-slate-800 rounded-lg p-3 mt-4 text-xs text-slate-400">
          <Info className="w-4 h-4 text-indigo-400 flex-shrink-0 mt-0.5" />
          <p>
            When selecting a strike range, multiple CSV files will be downloaded (one for each strike). Data includes OHLCV. 
          </p>
        </div>
      )}

      {success && (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 mt-4 text-emerald-300 text-sm">
          {success}
        </div>
      )}
      
      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 mt-4 text-rose-300 text-sm">
          {error}
        </div>
      )}
    </div>
  );
}
