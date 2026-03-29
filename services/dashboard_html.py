"""
Генерація односторінкового HTML-дашборду з даних заправок.
"""
from __future__ import annotations

import html as html_lib
import json
from datetime import datetime
from typing import List

from models.database import Refuel
from services.yearly_monthly_stats import aggregate_refuels_by_month


def _esc(s: str) -> str:
    return html_lib.escape(s, quote=True)


def _dec(x) -> float:
    if x is None:
        return 0.0
    return float(x)


def build_dashboard_page(
    refuels: List[Refuel],
    *,
    generated_at: datetime,
    expires_at: datetime,
    year: int,
) -> str:
    """Повна HTML-сторінка з таблицею та графіком витрат по місяцях за `year`."""
    report = aggregate_refuels_by_month(list(refuels), year)

    labels = []
    uah_vals = []
    names = [
        "",
        "Січ",
        "Лют",
        "Бер",
        "Кві",
        "Тра",
        "Чер",
        "Лип",
        "Сер",
        "Вер",
        "Жов",
        "Лис",
        "Гру",
    ]
    for m in report.months:
        labels.append(names[m.month])
        uah_vals.append(_dec(m.total_uah))

    chart_json = json.dumps({"labels": labels, "uah": uah_vals}, ensure_ascii=False)

    rows_html = []
    for r in sorted(refuels, key=lambda x: (x.date, x.id), reverse=True)[:500]:
        usd = f"${_dec(r.total_cost_usd):.2f}" if r.total_cost_usd is not None else "—"
        dist = str(r.distance_from_last) if r.distance_from_last is not None else "—"
        cons = f"{r.consumption:.2f}" if r.consumption is not None else "—"
        rows_html.append(
            "<tr>"
            f"<td>{r.date.strftime('%Y-%m-%d %H:%M')}</td>"
            f"<td>{_esc(r.station_name)}</td>"
            f"<td>{_esc(r.fuel_type)}</td>"
            f"<td class='num'>{r.liters:.2f}</td>"
            f"<td class='num'>{r.total_cost:.2f}</td>"
            f"<td class='num'>{usd}</td>"
            f"<td class='num'>{r.odometer}</td>"
            f"<td class='num'>{dist}</td>"
            f"<td class='num'>{cons}</td>"
            "</tr>"
        )

    total_note = ""
    if len(refuels) > 500:
        total_note = f"<p class='muted'>У таблиці показано останні 500 з {len(refuels)} записів.</p>"

    y_cons = (
        f"{report.avg_consumption_year:.2f}"
        if report.avg_consumption_year is not None
        else "—"
    )
    y_usd = f"${report.total_usd:.2f}" if report.usd_rows > 0 else "—"

    return f"""<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>FuelBot — дашборд {year}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root {{
  --bg: #0f1419;
  --card: #1a2332;
  --text: #e7ecf3;
  --muted: #8b9aab;
  --accent: #3b82f6;
  --border: #2d3a4d;
}}
* {{ box-sizing: border-box; }}
body {{
  font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
  margin: 0;
  padding: 1rem;
  line-height: 1.45;
}}
.wrap {{ max-width: 1100px; margin: 0 auto; }}
h1 {{ font-size: 1.35rem; margin: 0 0 0.5rem; }}
.muted {{ color: var(--muted); font-size: 0.88rem; }}
.banner {{
  background: linear-gradient(135deg, #1e3a5f 0%, var(--card) 100%);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 1rem 1.25rem;
  margin-bottom: 1.25rem;
}}
.kpi {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 0.75rem;
  margin-bottom: 1.25rem;
}}
.kpi div {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 0.85rem;
}}
.kpi .v {{ font-size: 1.25rem; font-weight: 600; color: var(--accent); }}
.chart-wrap {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 1rem;
  margin-bottom: 1.25rem;
  height: 280px;
}}
table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
}}
th, td {{ padding: 0.45rem 0.5rem; text-align: left; border-bottom: 1px solid var(--border); }}
th {{ background: #243044; position: sticky; top: 0; }}
tr:hover td {{ background: #1f2a3a; }}
.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.scroll {{ max-height: 480px; overflow: auto; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="banner">
    <h1>⛽ FuelBot — дашборд</h1>
    <p class="muted">Згенеровано: {generated_at.strftime('%Y-%m-%d %H:%M UTC')} · Сторінка дійсна до: <strong>{expires_at.strftime('%Y-%m-%d %H:%M UTC')}</strong> (макс. 24 год)</p>
    <p class="muted">Не пересилайте посилання стороннім — доступ лише за секретним токеном.</p>
  </div>

  <div class="kpi">
    <div><div class="muted">Рік</div><div class="v">{year}</div></div>
    <div><div class="muted">Заправок</div><div class="v">{report.total_refuels}</div></div>
    <div><div class="muted">Літрів</div><div class="v">{report.total_liters:.2f}</div></div>
    <div><div class="muted">Грн</div><div class="v">{report.total_uah:.2f}</div></div>
    <div><div class="muted">USD (де є)</div><div class="v">{y_usd}</div></div>
    <div><div class="muted">Пробіг км</div><div class="v">{report.total_km}</div></div>
    <div><div class="muted">Сер. л/100км</div><div class="v">{y_cons}</div></div>
  </div>

  <h2 class="muted" style="font-size:1rem;margin-bottom:0.5rem">Витрати за місяць ({year}), грн</h2>
  <div class="chart-wrap"><canvas id="ch"></canvas></div>

  <h2 class="muted" style="font-size:1rem;margin-bottom:0.5rem">Заправки (нові зверху)</h2>
  {total_note}
  <div class="scroll">
  <table>
    <thead>
      <tr>
        <th>Дата</th><th>АЗС</th><th>Паливо</th><th>Л</th><th>Грн</th><th>USD</th><th>Одом.</th><th>Км</th><th>л/100</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows_html)}
    </tbody>
  </table>
  </div>
</div>
<script>
const data = {chart_json};
const ctx = document.getElementById('ch');
new Chart(ctx, {{
  type: 'bar',
  data: {{
    labels: data.labels,
    datasets: [{{
      label: 'Грн',
      data: data.uah,
      backgroundColor: 'rgba(59, 130, 246, 0.55)',
      borderColor: 'rgba(59, 130, 246, 1)',
      borderWidth: 1
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      y: {{ ticks: {{ color: '#8b9aab' }}, grid: {{ color: '#2d3a4d' }} }},
      x: {{ ticks: {{ color: '#8b9aab' }}, grid: {{ display: false }} }}
    }}
  }}
}});
</script>
</body>
</html>
"""
