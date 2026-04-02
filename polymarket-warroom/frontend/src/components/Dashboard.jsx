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
  btnSmall: {
    padding: '3px 10px',
    border: '1px solid #ff4444',
    borderRadius: '3px',
    background: '#2a0a0a',
    color: '#ff4444',
    cursor: 'pointer',
    fontSize: '10px',
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
  badge: (type) => {
    const colors = {
      scalping: { bg: '#1a2a1a', fg: '#00ff88', border: '#00ff8833' },
      momentum: { bg: '#1a1a2a', fg: '#4488ff', border: '#4488ff33' },
      mean_reversion: { bg: '#2a2a1a', fg: '#ffcc44', border: '#ffcc4433' },
      manual: { bg: '#2a1a2a', fg: '#cc88ff', border: '#cc88ff33' },
    }
    const c = colors[type] || { bg: '#2a1a1a', fg: '#ff8844', border: '#ff884433' }
    return {
      padding: '2px 8px',
      borderRadius: '3px',
      fontSize: '10px',
      fontWeight: 'bold',
      background: c.bg,
      color: c.fg,
      border: `1px solid ${c.border}`,
    }
  },
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
  truncate: {
    maxWidth: '180px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
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

function fmtTime(iso) {
  if (!iso) return '-'
  return iso.split('T')[1]?.slice(0, 8) || '-'
}

function fmtDateTime(iso) {
  if (!iso) return '-'
  const d = iso.split('T')[0]?.slice(5) || ''
  const t = iso.split('T')[1]?.slice(0, 5) || ''
  return `${d} ${t}`
}

function Dashboard({ status, positions, trades, signals, activity, metrics, postMortem, connected, onAction, onRefresh }) {
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

      {/* Open Positions (full width with close button) */}
      <div style={{ ...styles.card, marginBottom: '16px' }}>
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
                <th style={styles.th}>Size</th>
                <th style={styles.th}>P&L</th>
                <th style={styles.th}>Strategy</th>
                <th style={styles.th}>Opened</th>
                <th style={styles.th}>Action</th>
              </tr>
            </thead>
            <tbody>
              {positions.map(p => (
                <tr key={p.id}>
                  <td style={{ ...styles.td, ...styles.truncate }} title={p.question}>
                    {p.question || p.market_id}
                  </td>
                  <td style={styles.td}>{p.direction === 'BUY_YES' ? 'YES' : 'NO'}</td>
                  <td style={styles.td}>{fmt(p.entry_price, 4)}</td>
                  <td style={styles.td}>{fmt(p.current_price, 4)}</td>
                  <td style={styles.td}>${fmt(p.position_size)}</td>
                  <td style={{ ...styles.td, ...pnlColor(p.pnl) }}>
                    {fmtUsd(p.pnl)} ({fmtPct(p.pnl_pct)})
                  </td>
                  <td style={styles.td}>
                    <span style={styles.badge(p.strategy)}>{p.strategy}</span>
                  </td>
                  <td style={styles.td}>{fmtDateTime(p.opened_at)}</td>
                  <td style={styles.td}>
                    <button
                      style={styles.btnSmall}
                      onClick={() => onAction('sell', { trade_id: p.id })}
                      title="Close this position"
                    >
                      CLOSE
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Signals + Trade History */}
      <div style={{ ...styles.grid, gridTemplateColumns: '1fr 1fr' }}>
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
                    <td style={{ ...styles.td, ...styles.truncate }}>
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

        {/* Recent Trades (enriched) */}
        <div style={styles.card}>
          <div style={styles.cardTitle}>Recent Trades</div>
          {trades.length === 0 ? (
            <div style={{ color: '#444', fontSize: '12px' }}>No closed trades</div>
          ) : (
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>Market</th>
                  <th style={styles.th}>Dir</th>
                  <th style={styles.th}>Strategy</th>
                  <th style={styles.th}>Entry</th>
                  <th style={styles.th}>Exit</th>
                  <th style={styles.th}>P&L</th>
                  <th style={styles.th}>Reason</th>
                  <th style={styles.th}>Closed At</th>
                </tr>
              </thead>
              <tbody>
                {trades.slice(-20).reverse().map(t => (
                  <tr key={t.id}>
                    <td style={{ ...styles.td, ...styles.truncate }} title={t.question}>
                      {t.question || t.market_id?.slice(0, 12)}
                    </td>
                    <td style={styles.td}>
                      {t.direction === 'BUY_YES' ? 'YES' : t.direction === 'BUY_NO' ? 'NO' : '-'}
                    </td>
                    <td style={styles.td}>
                      <span style={styles.badge(t.strategy)}>{t.strategy || '-'}</span>
                    </td>
                    <td style={styles.td}>{fmt(t.entry_price, 4)}</td>
                    <td style={styles.td}>{fmt(t.exit_price, 4)}</td>
                    <td style={{ ...styles.td, ...pnlColor(t.pnl) }}>{fmtUsd(t.pnl)}</td>
                    <td style={styles.td}>{t.reason}</td>
                    <td style={styles.td}>{fmtDateTime(t.closed_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Post-Mortem Analysis + Activity Log */}
      <div style={{ ...styles.grid, gridTemplateColumns: '1fr 1fr', marginTop: '16px' }}>
        {/* Post-Mortem Analysis */}
        <div style={styles.card}>
          <div style={styles.cardTitle}>Trade Post-Mortem</div>
          {!postMortem || postMortem.total_trades === 0 ? (
            <div style={{ color: '#444', fontSize: '12px' }}>No trade analysis yet</div>
          ) : (
            <div>
              {/* Summary stats */}
              <div style={{ display: 'flex', gap: '16px', marginBottom: '12px', fontSize: '12px' }}>
                <div>
                  <span style={{ color: '#888' }}>WR: </span>
                  <span style={pnlColor(postMortem.win_rate > 0.5 ? 1 : -1)}>
                    {fmtPct(postMortem.win_rate)}
                  </span>
                </div>
                <div>
                  <span style={{ color: '#888' }}>Avg Win: </span>
                  <span style={styles.positive}>{fmtUsd(postMortem.avg_win)}</span>
                </div>
                <div>
                  <span style={{ color: '#888' }}>Avg Loss: </span>
                  <span style={styles.negative}>{fmtUsd(postMortem.avg_loss)}</span>
                </div>
              </div>

              {/* Loss patterns */}
              {postMortem.loss_analysis?.patterns?.length > 0 && (
                <div style={{ marginBottom: '12px' }}>
                  <div style={{ fontSize: '11px', color: '#ff8844', marginBottom: '6px' }}>PATTERNS DETECTED:</div>
                  {postMortem.loss_analysis.patterns.map((p, i) => (
                    <div key={i} style={{ fontSize: '11px', padding: '4px 0', borderBottom: '1px solid #1a1a2e' }}>
                      <span style={{ color: '#ff4444' }}>[{p.type}]</span>{' '}
                      {p.recommendation}
                    </div>
                  ))}
                </div>
              )}

              {/* Recent post-mortems */}
              <div style={{ ...styles.activityLog, maxHeight: '200px' }}>
                {(postMortem.recent_post_mortems || []).slice().reverse().map((pm, i) => (
                  <div key={i} style={{ ...styles.logEntry, flexDirection: 'column', gap: '2px', padding: '4px 0' }}>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                      <span style={{
                        ...styles.badge(pm.strategy),
                        fontSize: '9px',
                      }}>{pm.strategy}</span>
                      <span style={pnlColor(pm.pnl)}>{fmtUsd(pm.pnl)}</span>
                      <span style={{ color: '#666', fontSize: '10px' }}>
                        [{pm.category}] {pm.reason}
                      </span>
                      <span style={{ color: '#444', fontSize: '10px', marginLeft: 'auto' }}>
                        {fmtTime(pm.closed_at)}
                      </span>
                    </div>
                    <div style={{ fontSize: '10px', color: '#888', paddingLeft: '4px' }}>
                      {pm.diagnosis}
                    </div>
                  </div>
                ))}
              </div>

              {/* System failures */}
              {postMortem.system_failures?.length > 0 && (
                <div style={{ marginTop: '12px' }}>
                  <div style={{ fontSize: '11px', color: '#ff4444', marginBottom: '4px' }}>
                    SYSTEM FAILURES ({postMortem.system_failures.length})
                  </div>
                  {postMortem.system_failures.slice(-5).reverse().map((f, i) => (
                    <div key={i} style={{ fontSize: '10px', color: '#ff6666', padding: '2px 0' }}>
                      [{fmtTime(f.timestamp)}] {f.component}: {f.error}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Activity Log */}
        <div style={styles.card}>
          <div style={styles.cardTitle}>Activity Log</div>
          <div style={styles.activityLog}>
            {activity.slice().reverse().map((a, i) => (
              <div key={i} style={styles.logEntry}>
                <span style={styles.logTime}>
                  {fmtTime(a.timestamp)}
                </span>
                <span style={{
                  ...styles.logAgent,
                  color: a.agent === 'post_mortem' ? '#ff8844'
                    : a.agent === 'system_failure' ? '#ff4444'
                    : '#4488ff'
                }}>[{a.agent}]</span>
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
