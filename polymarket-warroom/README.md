# Polymarket War Room

AI-powered market analysis system for Polymarket. Scans all categories, identifies short-term directional trading opportunities on binary outcome contracts, and executes trades via paper trading (with live trading toggle for later).

## Quick Start

### Backend

```bash
cd polymarket-warroom
pip install -r requirements.txt
cp .env.example .env
uvicorn backend.main:app --reload
```

### CLI War Room

```bash
python -m cli.warroom
```

### Web Dashboard

```bash
cd frontend
npm install
npm run dev
```

### Docker

```bash
docker compose up
```

- Backend: http://localhost:8000
- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs

## Architecture

```
Scanner Agent → Analyst Agent → Risk Manager → Executor
     ↓              ↓               ↓            ↓
  All markets   Trade signals   Position     Paper/Live
  scanned       with EV calc    sizing       execution
```

**Agents:**
- **Scanner** — polls all active Polymarket markets, filters by liquidity/volume/spread, scores opportunities
- **Analyst** — runs momentum, mean reversion, volume spike, and EV strategies on flagged markets
- **Risk Manager** — enforces position limits (5% max per position, 40% max exposure, 5% daily loss limit), quarter-Kelly sizing
- **Executor** — orchestrates the pipeline, executes paper trades with simulated slippage

**Strategies:**
- Momentum — sustained price movement detection
- Mean Reversion — overreaction fading
- Volume Spike — unusual volume without price movement (pending breakout)
- Edge Detector — expected value calculator, minimum 2% EV threshold

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/status` | System status |
| GET | `/api/portfolio` | Portfolio state |
| GET | `/api/signals` | Scanner signals |
| GET | `/api/positions` | Open positions |
| GET | `/api/trades` | Trade history |
| GET | `/api/activity` | Agent activity log |
| GET | `/api/stats` | Analytics |
| GET | `/api/snapshots` | Portfolio chart data |
| POST | `/api/scan` | Force scan |
| POST | `/api/buy` | Manual buy |
| POST | `/api/sell` | Close position |
| POST | `/api/halt` | Kill switch |
| POST | `/api/resume` | Resume trading |
| WS | `/ws` | Real-time updates |

## CLI Commands

| Command | Description |
|---------|-------------|
| `scan` | Force immediate market scan |
| `buy <market_id> <YES/NO> <amount>` | Manual trade |
| `sell <trade_id>` | Close position |
| `halt` | Kill switch |
| `resume` | Resume after halt |
| `status` | Portfolio summary |
| `detail <market_id>` | Market deep dive |
| `config <key> <value>` | Change settings |

## Risk Disclaimer

This is a trading tool, not financial advice. Paper trade extensively before considering live funds. All trading involves risk of loss.
