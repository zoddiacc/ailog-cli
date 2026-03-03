"""
HTML report generation for AILog sessions.
"""

import html
import re


def _text_to_html(text):
    """Convert AI analysis text to HTML, preserving structure."""
    text = html.escape(text)

    # Convert ``` code blocks to <pre>
    text = re.sub(
        r'```(\w*)\n(.*?)```',
        lambda m: f'<pre class="code-block">{m.group(2)}</pre>',
        text,
        flags=re.DOTALL,
    )

    # Bold section headers (lines like "ROOT CAUSE:", "HOW TO FIX:", etc.)
    text = re.sub(
        r'^((?:ROOT CAUSE|WHAT WENT WRONG|HOW TO FIX|FIX|TIP|CONTEXT)[^\n]*)',
        r'<strong class="section-header">\1</strong>',
        text,
        flags=re.MULTILINE | re.IGNORECASE,
    )

    # Newlines to <br> (but not inside <pre>)
    parts = re.split(r'(<pre.*?</pre>)', text, flags=re.DOTALL)
    for i, part in enumerate(parts):
        if not part.startswith('<pre'):
            parts[i] = part.replace('\n', '<br>\n')
    text = ''.join(parts)

    return text


def generate_html_report(data):
    """
    Generate a self-contained HTML report string.

    data dict keys:
        stats: dict with errors, warnings, filtered, lines, provider
        crashes: list of (metadata_dict, ai_analysis_str)
        batch_analyses: list of (title, content)
        summary: str or None
        config: dict with provider, model, noise_level, etc.
        timestamp: str
    """
    stats = data.get('stats', {})
    crashes = data.get('crashes', [])
    batch_analyses = data.get('batch_analyses', [])
    summary = data.get('summary', '')
    config = data.get('config', {})
    timestamp = html.escape(data.get('timestamp', ''))

    # Build crashes HTML
    crashes_html = ''
    if crashes:
        for i, (meta, analysis) in enumerate(crashes, 1):
            meta_rows = ''
            for key, label in [
                ('exception', 'Exception'),
                ('thread', 'Thread'),
                ('process', 'Process'),
                ('location', 'Location'),
                ('method', 'Method'),
                ('source_file', 'Source'),
            ]:
                val = meta.get(key)
                if val:
                    meta_rows += (
                        f'<tr><td class="meta-label">{html.escape(label)}</td>'
                        f'<td class="meta-value">{html.escape(str(val))}</td></tr>\n'
                    )

            crashes_html += f'''
            <div class="crash-card">
                <div class="crash-title">Crash #{i}</div>
                <table class="meta-table">{meta_rows}</table>
                <div class="analysis">{_text_to_html(analysis)}</div>
            </div>
            '''
    else:
        crashes_html = '<p class="clean-msg">No crashes detected during this session.</p>'

    # Build batch analyses HTML
    batch_html = ''
    if batch_analyses:
        for title, content in batch_analyses:
            batch_html += f'''
            <div class="batch-card">
                <div class="batch-title">{html.escape(title)}</div>
                <div class="analysis">{_text_to_html(content)}</div>
            </div>
            '''

    # Build summary HTML
    summary_html = ''
    if summary:
        summary_html = f'''
        <div class="section">
            <h2>Session Summary</h2>
            <div class="summary-box">{_text_to_html(summary)}</div>
        </div>
        '''
    else:
        summary_html = '''
        <div class="section">
            <h2>Session Summary</h2>
            <p class="clean-msg">Clean session &mdash; no errors or warnings detected.</p>
        </div>
        '''

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AILog Report &mdash; {timestamp}</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        background: #1a1a2e; color: #e0e0e0; padding: 2rem; line-height: 1.6;
    }}
    .container {{ max-width: 900px; margin: 0 auto; }}
    h1 {{ color: #00d4ff; font-size: 1.8rem; margin-bottom: 0.3rem; }}
    .timestamp {{ color: #888; font-size: 0.9rem; margin-bottom: 1.5rem; }}
    h2 {{ color: #00d4ff; font-size: 1.3rem; margin-bottom: 1rem; border-bottom: 1px solid #333; padding-bottom: 0.5rem; }}
    .stats-bar {{
        display: flex; gap: 1.5rem; flex-wrap: wrap;
        background: #16213e; border-radius: 8px; padding: 1rem 1.5rem; margin-bottom: 2rem;
    }}
    .stat {{ text-align: center; }}
    .stat-value {{ font-size: 1.5rem; font-weight: 700; }}
    .stat-label {{ font-size: 0.75rem; text-transform: uppercase; color: #888; }}
    .stat-crashes .stat-value {{ color: #ff6b6b; }}
    .stat-errors .stat-value {{ color: #ff8a8a; }}
    .stat-warnings .stat-value {{ color: #ffd93d; }}
    .stat-filtered .stat-value {{ color: #c084fc; }}
    .stat-lines .stat-value {{ color: #67e8f9; }}
    .section {{ margin-bottom: 2rem; }}
    .crash-card, .batch-card {{
        background: #16213e; border-radius: 8px; padding: 1.5rem; margin-bottom: 1rem;
        border-left: 4px solid #ff6b6b;
    }}
    .batch-card {{ border-left-color: #ffd93d; }}
    .crash-title {{ font-weight: 700; color: #ff6b6b; font-size: 1.1rem; margin-bottom: 0.8rem; }}
    .batch-title {{ font-weight: 700; color: #ffd93d; font-size: 1.1rem; margin-bottom: 0.8rem; }}
    .meta-table {{ margin-bottom: 1rem; }}
    .meta-table td {{ padding: 0.2rem 0; }}
    .meta-label {{ color: #888; font-weight: 600; padding-right: 1rem; white-space: nowrap; vertical-align: top; }}
    .meta-value {{ color: #e0e0e0; word-break: break-word; }}
    .analysis {{ color: #ccc; }}
    .section-header {{ color: #ffd93d; display: block; margin-top: 0.5rem; }}
    .code-block {{
        background: #0d1117; border-radius: 4px; padding: 0.8rem; margin: 0.5rem 0;
        font-family: "Fira Code", "Cascadia Code", monospace; font-size: 0.85rem;
        overflow-x: auto; color: #c9d1d9;
    }}
    .summary-box {{
        background: #16213e; border-radius: 8px; padding: 1.5rem;
        border-left: 4px solid #00d4ff;
    }}
    .clean-msg {{ color: #4ade80; font-style: italic; padding: 1rem 0; }}
    .config {{ color: #666; font-size: 0.8rem; margin-top: 2rem; text-align: center; }}
</style>
</head>
<body>
<div class="container">
    <h1>AILog Session Report</h1>
    <div class="timestamp">{timestamp}</div>

    <div class="stats-bar">
        <div class="stat stat-crashes">
            <div class="stat-value">{stats.get('crashes', 0)}</div>
            <div class="stat-label">Crashes</div>
        </div>
        <div class="stat stat-errors">
            <div class="stat-value">{stats.get('errors', 0)}</div>
            <div class="stat-label">Errors</div>
        </div>
        <div class="stat stat-warnings">
            <div class="stat-value">{stats.get('warnings', 0)}</div>
            <div class="stat-label">Warnings</div>
        </div>
        <div class="stat stat-filtered">
            <div class="stat-value">{stats.get('filtered', 0)}</div>
            <div class="stat-label">Filtered</div>
        </div>
        <div class="stat stat-lines">
            <div class="stat-value">{stats.get('lines', 0)}</div>
            <div class="stat-label">Total Lines</div>
        </div>
    </div>

    <div class="section">
        <h2>Crashes</h2>
        {crashes_html}
    </div>

    {f"""<div class="section">
        <h2>Batch Analyses</h2>
        {batch_html}
    </div>""" if batch_analyses else ""}

    {summary_html}

    <div class="config">
        Provider: {html.escape(str(config.get('provider', 'N/A')))}
        &middot; Model: {html.escape(str(config.get('model', 'N/A')))}
        &middot; Noise level: {html.escape(str(config.get('noise_level', 'N/A')))}
        &middot; Generated by AILog
    </div>
</div>
</body>
</html>'''
