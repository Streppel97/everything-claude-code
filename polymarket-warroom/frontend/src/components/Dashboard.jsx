import React from 'react'

const styles = {
  app: {
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
    background: '#0a0a0f',
    color: '#e0e0e0',
    minHeight: '100vh',
    padding: '16px',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '20px',
    borderBottom: '1px solid #1a1a2e',
    paddingBottom: '12px',
  },
  title: {
    fontSize: '20px',
    fontWeight: 'bold',
    color: '#00ff88',
  },
  controls: { display: 'flex', gap: '8px', alignItems: 'center' },
  btn: {
    padding: '6px 16px',
    border: '1px solid #333',
    borderRadius: '4px',
    background: '#1a1a2e',
    color: '#e0e0e0',
    cursor: 'pointer',
    fontSize: '12px',
    fontFamily: 'inherit',
  },
  btnDanger: {
    padding: '6px 16px',
    border: '1px solid #ff4444',
    borderRadius: '4px',
    background: '#2a0a0a',
    color: '#ff4444',
    cursor: 'pointer',
    fontSize: '12px',
    fontFamily: 'inherit',
  },
  btnSuccess: {
    padding: '6px 16px',
    border: '1px solid #00ff88',
    borderRadius: '4px',
    background: '#0a2a1a',
    color: '#00ff88',
    cursor: 'pointer',
    fontSize: '12px',
    fontFamily: 'inherit',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
    gap: '16px',
    marginBottom: '16px',
  },
  card: {
    background: '#12121f',
    border: '1px solid #1a1a2e',
    borderRadius: '8px',
    padding: '16px',
  },
  cardTitle: {
    fontSize: '13px',
    color: '#888',
    textTransform: 'uppercase',
    letterSpacing: '1px',
    marginBottom: '12px',
  },
  stat: {
    fontSize: '24px',
    fontWeight: 'bold',
  },
  statLabel: {
    fontSize: '11px',
    color: '#666',
    marginTop: '2px',
  },
  statRow: {
    display: 'flex',
    justifyContent: 'space-between',
    padding: '4px 0',
    borderBottom: '1px solid #1a1a2e',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: '12px',
  },
  th: {
    textAlign: 'left',
    padding: '8px 6px',
    borderBottom: '2px solid #1a1a2e',
    color: '#888',
    fontSize: '11px',
    textTransform: 'uppercase',
  },
  td: {
    padding: '6px',
    borderBottom: '1px solid #0f0f1a',
  },
  positive: { color: '#00ff88' },
  negative: { color: '#ff4444' },
  neutral: { color: '#888' },
  dot: (connected) => ({
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    background: connected ? '#00ff88' : '#ff4444',
    display: 'inline-block',
  }),
  badge: (type) => ({
    padding: '2px 8px',
    borderRadius: '3px',
    fontSize: '10px',
    fontWeight: 'bold',
    background: type === 'scalping' ? '#1a2a1a' : type === 'momentum' ? '#1a1a2a' : '#2a1a1a',
    color: type === 'scalping' ? '#00ff88' : type === 'momentum' ? '#4488ff' : '#ff8844',
    border: `1px solid ${type === 'scalping' ? '#00ff8833' : type === 'momentum' ? '#4488ff33' : '#ff884433'}`,
  }),
  activityLog: {
    maxHeight: '300px',
    overflowY: 'auto',
    fontSize: '11px',
    fontFamily: 'inherit',
  },
  logEntry: {
    padding: '3px 0',
    borderBottom: '1px solid #0f0f1a',
    display: 'flex',
    gap: '8px',
  },
  logTime: { color: '#444', minWidth: '70px' },
  logAgent: { color: '#4488ff', minWidth: '80px' },
}

function pnlColor(val) {
  if (val > 0) return styles.positive
  if (val < 0) return styles.negative
  return styles.neutral
}

function fmt(val, decimals = 2) {
  if (val == null) return '-'
  return typeof val === 'number' ? val.toFixed(decimals) : String(val)
}

function fmtUsd(val) {
  if (val == null) return '-'
  const prefix = val >= 0 ? '+$' : '-$'
  return `${prefix}${Math.abs(val).toFixed(2)}`
}

function fmtPct(val) {
  if (val == null) return '-'
  return `${(val * 100).toFixed(1)}%`
}

function Dashboard({ status, positions, trades, signals, activity, metrics, connected, onAction, onRefresh }) {
  const portfolio = status?.portfolio || {}
  const totalValue = portfolio.total_value || 0
  const totalPnl = portfolio.total_pnl || 0
  const pnlPct = portfolio.initial_balance ? totalPnl / portfolio.initial_balance : 0

  return (
    <div style={styles.app}>
      {/* Header */}
      <div style={styles.header}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={styles.title}>POLYMARKET WAR ROOM</span>
          <span style={styles.dot(connected)} title={connected ? 'Connected' : 'Disconnected'} />
          {status?.halted && <span style={{ color: '#ff4444', fontSize: '12px' }}>HALTED</span>}
          {status?.running && <span style={{ color: '#00ff88', fontSize: '12px' }}>LIVE</span>}
        </div>
        <div style={styles.controls}>
          <span style={{ fontSize: '11px', color: '#666' }}>
            {status?.mode?.toUpperCase() || 'PAPER'} MODE
          </span>
          {!status?.running ? (
            <button style={styles.btnSuccess} onClick={() => onAction('start')}>Start</button>
          ) : (
            <button style={styles.btn} onClick={() => onAction('stop')}>Stop</button>
          )}
          {!status?.halted ? (
            <button style={styles.btnDanger} onClick={() => onAction('halt')}>KILL</button>
          ) : (
            <button style={styles.btnSuccess} onClick={() => onAction('resume')}>Resume</button>
          )}
          <button style={styles.btn} onClick={onRefresh}>Refresh</button>
        </div>
      </div>

      {/* Portfolio Stats */}
      <div style={styles.grid}>
        <div style={styles.card}>
          <div style={styles.cardTitle}>Portfolio Value</div>
          <div style={styles.stat}>${fmt(totalValue)}</div>
          <div style={styles.statLabel}>Cash: ${fmt(portfolio.cash)}</div>
        </div>
        <div style={styles.card}>
          <div style={styles.cardTitle}>Total P&L</div>
          <div style={{ ...styles.stat, ...pnlColor(totalPnl) }}>
            {fmtUsd(totalPnl)}
          </div>
          <div style={{ ...styles.statLabel, ...pnlColor(pnlPct) }}>
            {fmtPct(pnlPct)} return
          </div>
        </div>
        <div style={styles.card}>
          <div style={styles.cardTitle}>Open Positions</div>
          <div style={styles.stat}>{positions.length}</div>
          <div style={styles.statLabel}>
            Scans: {status?.scan_count || 0} | Analyses: {status?.analysis_count || 0}
          </div>
        </div>
        <div style={styles.card}>
          <div style={styles.cardTitle}>Scalp Metrics</div>
          <div style={styles.stat}>
            {metrics?.win_rate != null ? fmtPct(metrics.win_rate) : '-'} WR
          </div>
          <div style={styles.statLabel}>
            {metrics?.total_cycles || 0} cycles | PF: {fmt(metrics?.profit_factor)}
          </div>
        </div>
      </div>

      {/* Strategy Breakdown */}
      {metrics?.strategy_breakdown && Object.keys(metrics.strategy_breakdown).length > 0 && (
        <div style={{ ...styles.card, marginBottom: '16px' }}>
          <div style={styles.cardTitle}>Strategy Breakdown</div>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Strategy</th>
                <th style={styles.th}>Trades</th>
                <th style={styles.th}>Win Rate</th>
                <th style={styles.th}>P&L</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(metrics.strategy_breakdown).map(([name, data]) => (
                <tr key={name}>
                  <td style={styles.td}>
                    <span style={styles.badge(name)}>{name}</span>
                  </td>
                  <td style={styles.td}>{data.trades}</td>
                  <td style={styles.td}>
                    {data.trades > 0 ? fmtPct(data.wins / data.trades) : '-'}
                  </td>
                  <td style={{ ...styles.td, ...pnlColor(data.pnl) }}>
                    {fmtUsd(data.pnl)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Positions + Signals */}
      <div style={{ ...styles.grid, gridTemplateColumns: '1fr 1fr' }}>
        {/* Open Positions */}
        <div style={styles.card}>
          <div style={styles.cardTitle}>Open Positions</div>
          {positions.length === 0 ? (
            <div style={{ color: '#444', fontSize: '12px' }}>No open positions</div>
          ) : (
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>Market</th>
                  <th style={styles.th}>Dir</th>
                  <th style={styles.th}>Entry</th>
                  <th style={styles.th}>Current</th>
                  <th style={styles.th}>P&L</th>
                  <th style={styles.th}>Strategy</th>
                </tr>
              </thead>
              <tbody>
                {positions.map(p => (
                  <tr key={p.id}>
                    <td style={{ ...styles.td, maxWidth: '180px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                        title={p.question}>
                      {p.question || p.market_id}
                    </td>
                    <td style={styles.td}>{p.direction === 'BUY_YES' ? 'YES' : 'NO'}</td>
                    <td style={styles.td}>{fmt(p.entry_price, 4)}</td>
                    <td style={styles.td}>{fmt(p.current_price, 4)}</td>
                    <td style={{ ...styles.td, ...pnlColor(p.pnl) }}>
                      {fmtUsd(p.pnl)} ({fmtPct(p.pnl_pct)})
                    </td>
                    <td style={styles.td}>
                      <span style={styles.badge(p.strategy)}>{p.strategy}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Latest Signals */}
        <div style={styles.card}>
          <div style={styles.cardTitle}>Latest Signals</div>
          {signals.length === 0 ? (
            <div style={{ color: '#444', fontSize: '12px' }}>No signals yet</div>
          ) : (
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>Market</th>
                  <th style={styles.th}>Dir</th>
                  <th style={styles.th}>Conf</th>
                  <th style={styles.th}>EV</th>
                  <th style={styles.th}>Strategy</th>
                </tr>
              </thead>
              <tbody>
                {signals.slice(0, 10).map((s, i) => (
                  <tr key={i}>
                    <td style={{ ...styles.td, maxWidth: '160px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {s.market_id.slice(0, 12)}...
                    </td>
                    <td style={styles.td}>{s.direction === 'BUY_YES' ? 'YES' : 'NO'}</td>
                    <td style={styles.td}>{fmtPct(s.confidence)}</td>
                    <td style={{ ...styles.td, ...pnlColor(s.ev) }}>{fmt(s.ev, 4)}</td>
                    <td style={styles.td}>
                      <span style={styles.badge(s.strategy)}>{s.strategy}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Trade History + Activity Log */}
      <div style={{ ...styles.grid, gridTemplateColumns: '1fr 1fr', marginTop: '16px' }}>
        {/* Recent Trades */}
        <div style={styles.card}>
          <div style={styles.cardTitle}>Recent Trades</div>
          {trades.length === 0 ? (
            <div style={{ color: '#444', fontSize: '12px' }}>No closed trades</div>
          ) : (
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>#</th>
                  <th style={styles.th}>Entry</th>
                  <th style={styles.th}>Exit</th>
                  <th style={styles.th}>Size</th>
                  <th style={styles.th}>P&L</th>
                  <th style={styles.th}>Reason</th>
                </tr>
              </thead>
              <tbody>
                {trades.slice(-20).reverse().map(t => (
                  <tr key={t.id}>
                    <td style={styles.td}>{t.id}</td>
                    <td style={styles.td}>{fmt(t.entry_price, 4)}</td>
                    <td style={styles.td}>{fmt(t.exit_price, 4)}</td>
                    <td style={styles.td}>${fmt(t.position_size)}</td>
                    <td style={{ ...styles.td, ...pnlColor(t.pnl) }}>{fmtUsd(t.pnl)}</td>
                    <td style={styles.td}>{t.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Activity Log */}
        <div style={styles.card}>
          <div style={styles.cardTitle}>Activity Log</div>
          <div style={styles.activityLog}>
            {activity.slice().reverse().map((a, i) => (
              <div key={i} style={styles.logEntry}>
                <span style={styles.logTime}>
                  {a.timestamp ? a.timestamp.split('T')[1]?.slice(0, 8) : ''}
                </span>
                <span style={styles.logAgent}>[{a.agent}]</span>
                <span>{a.message}</span>
              </div>
            ))}
            {activity.length === 0 && (
              <div style={{ color: '#444' }}>No activity yet — start the pipeline</div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default Dashboard
