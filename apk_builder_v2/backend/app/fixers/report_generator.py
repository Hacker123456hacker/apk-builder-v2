"""
Fix Report Generator — produces a human-readable HTML report and
a machine-readable JSON report of all fixes applied to a project.
"""
import json
import os
from datetime import datetime
from typing import List
from .base import FixResult, Severity


def generate_json_report(
    project_name: str,
    project_type: str,
    build_status: str,
    fix_results: List[FixResult],
    ai_analysis: dict = None,
) -> str:
    """Returns a JSON string."""
    data = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "project_name": project_name,
        "project_type": project_type,
        "build_status": build_status,
        "summary": {
            "total_issues": len(fix_results),
            "total_fixed": sum(1 for r in fix_results if r.fixed),
            "by_category": _count_by_category(fix_results),
            "by_severity": _count_by_severity(fix_results),
        },
        "fixes": [r.to_dict() for r in fix_results],
        "ai_analysis": ai_analysis or {},
    }
    return json.dumps(data, indent=2)


def generate_html_report(
    project_name: str,
    project_type: str,
    build_status: str,
    fix_results: List[FixResult],
    ai_analysis: dict = None,
    build_url: str = None,
    retry_count: int = 0,
) -> str:
    """Returns a full HTML string for a downloadable fix report."""
    total = len(fix_results)
    fixed = sum(1 for r in fix_results if r.fixed)
    critical = sum(1 for r in fix_results if r.severity == Severity.CRITICAL)

    status_color = {
        "succeeded": "#22C55E", "failed": "#EF4444",
        "error": "#EF4444", "cancelled": "#F59E0B",
    }.get(build_status, "#94A3B8")

    rows = ""
    for r in fix_results:
        sev_color = {
            Severity.CRITICAL: "#EF4444", Severity.HIGH: "#F59E0B",
            Severity.MEDIUM: "#3B82F6", Severity.LOW: "#94A3B8",
        }.get(r.severity, "#94A3B8")
        fixed_label = "✓ Fixed" if r.fixed else "⚠ Detected (manual fix needed)"
        fixed_color = "#22C55E" if r.fixed else "#F59E0B"
        rows += f"""
        <tr>
          <td><span class="badge" style="background:{sev_color}22;color:{sev_color}">{r.severity.value.upper()}</span></td>
          <td><strong>{_esc(r.category)}</strong></td>
          <td>{_esc(r.file_path)}</td>
          <td>{_esc(r.issue)}</td>
          <td>{_esc(r.fix)}</td>
          <td style="color:{fixed_color};font-weight:600">{fixed_label}</td>
        </tr>
        """

    ai_section = ""
    if ai_analysis and ai_analysis.get("matched_errors"):
        suggestions = ""
        for e in ai_analysis["matched_errors"]:
            suggestions += f"""
            <div class="ai-error">
              <div class="ai-error-header">[{_esc(e.get("category",""))}] {_esc(e.get("summary",""))}</div>
              <div class="ai-suggestion">💡 {_esc(e.get("suggestion",""))}</div>
            </div>
            """
        ai_section = f"""
        <section class="section">
          <h2>🤖 AI Error Analysis</h2>
          <div class="ai-summary-box">{_esc(ai_analysis.get("summary",""))}</div>
          {suggestions}
        </section>
        """

    retry_section = ""
    if retry_count > 0:
        retry_section = f'<div class="retry-note">🔁 Build was retried <strong>{retry_count}</strong> time(s) with auto-fixes applied between attempts.</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Fix Report — {_esc(project_name)}</title>
<style>
  body {{ font-family: -apple-system, sans-serif; background: #0D0F12; color: #EDEEF0; margin: 0; padding: 24px; }}
  .header {{ background: #15181D; border: 1px solid #262B33; border-radius: 12px; padding: 24px; margin-bottom: 24px; }}
  h1 {{ font-size: 22px; margin: 0 0 6px; }}
  .meta {{ color: #9AA1AC; font-size: 13px; }}
  .status-pill {{ display: inline-block; padding: 4px 12px; border-radius: 20px; font-weight: 700; font-size: 12px; }}
  .stats {{ display: flex; gap: 16px; margin-top: 16px; flex-wrap: wrap; }}
  .stat {{ background: #1B1F26; border: 1px solid #262B33; border-radius: 10px; padding: 12px 18px; }}
  .stat-num {{ font-size: 28px; font-weight: 800; }}
  .stat-label {{ font-size: 12px; color: #9AA1AC; }}
  .section {{ background: #15181D; border: 1px solid #262B33; border-radius: 12px; padding: 20px; margin-bottom: 20px; }}
  h2 {{ font-size: 16px; margin: 0 0 16px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12.5px; }}
  th {{ text-align: left; padding: 10px; border-bottom: 1px solid #262B33; color: #9AA1AC; font-weight: 600; }}
  td {{ padding: 10px; border-bottom: 1px solid #1B1F26; vertical-align: top; }}
  .badge {{ padding: 2px 8px; border-radius: 5px; font-size: 10px; font-weight: 700; }}
  .ai-error {{ background: #1B1F26; border-radius: 8px; padding: 12px; margin-bottom: 10px; }}
  .ai-error-header {{ font-weight: 600; color: #EF4444; margin-bottom: 6px; font-size: 13px; }}
  .ai-suggestion {{ color: #EDEEF0; font-size: 12.5px; line-height: 1.5; }}
  .ai-summary-box {{ background: #1B1F26; border-left: 3px solid #EF4444; padding: 12px; border-radius: 6px; margin-bottom: 14px; font-size: 13px; }}
  .retry-note {{ background: rgba(79,155,242,0.1); border: 1px solid rgba(79,155,242,0.3); border-radius: 8px; padding: 10px 14px; font-size: 13px; margin-bottom: 16px; }}
  a {{ color: #3DDC84; }}
</style>
</head>
<body>
<div class="header">
  <h1>📋 Fix Report — {_esc(project_name)}</h1>
  <div class="meta">
    Project type: {_esc(project_type)} &nbsp;·&nbsp;
    Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} &nbsp;·&nbsp;
    Build: <span class="status-pill" style="background:{status_color}22;color:{status_color}">{_esc(build_status.upper())}</span>
    {f'&nbsp;·&nbsp; <a href="{build_url}" target="_blank">View on GitHub ↗</a>' if build_url else ''}
  </div>
  <div class="stats">
    <div class="stat"><div class="stat-num">{total}</div><div class="stat-label">Issues Found</div></div>
    <div class="stat"><div class="stat-num" style="color:#22C55E">{fixed}</div><div class="stat-label">Auto-Fixed</div></div>
    <div class="stat"><div class="stat-num" style="color:#EF4444">{critical}</div><div class="stat-label">Critical</div></div>
    <div class="stat"><div class="stat-num" style="color:#F59E0B">{total - fixed}</div><div class="stat-label">Manual Fix Needed</div></div>
  </div>
</div>

{retry_section}

<section class="section">
  <h2>🔧 Applied Fixes</h2>
  {f'<p style="color:#9AA1AC;font-size:13px">No issues detected — project was already clean.</p>' if not fix_results else ''}
  {f'''<table>
    <thead><tr>
      <th>Severity</th><th>Category</th><th>File</th>
      <th>Issue</th><th>Fix Applied</th><th>Status</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>''' if fix_results else ''}
</section>

{ai_section}

</body>
</html>"""


def _esc(s: str) -> str:
    if not s:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _count_by_category(results: List[FixResult]) -> dict:
    out = {}
    for r in results:
        out[r.category] = out.get(r.category, 0) + 1
    return out


def _count_by_severity(results: List[FixResult]) -> dict:
    out = {}
    for r in results:
        out[r.severity.value] = out.get(r.severity.value, 0) + 1
    return out
