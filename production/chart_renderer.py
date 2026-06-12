"""
Chart Renderer - Headless Technical Charting
=============================================
Renders candlestick charts with SMC annotations for Telegram broadcast.
Uses matplotlib with Agg backend (no display required).

When matplotlib is unavailable, falls back gracefully with a log warning.
"""

import logging
import os
import io
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

log = logging.getLogger('ChartRenderer')

CHART_DIR = Path(__file__).parent.parent / 'content' / 'charts'
CHART_DIR.mkdir(parents=True, exist_ok=True)

# Attempt matplotlib import; system works without it
HAS_MPL = False
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.patches import Rectangle, FancyBboxPatch
    HAS_MPL = True
except ImportError:
    log.info("matplotlib not installed — chart rendering disabled")
except Exception as e:
    log.debug(f"matplotlib init failed: {e}")


def render_signal_chart(
    symbol: str,
    tf: str,
    direction: str,
    score: int,
    candles: List[Dict],
    fvg_zone: Optional[tuple] = None,
    ob_zone: Optional[tuple] = None,
    entry_price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
) -> Optional[bytes]:
    """
    Render a candlestick chart with SMC annotations.

    Parameters:
        candles: list of dicts with 'time', 'open', 'high', 'low', 'close'
        fvg_zone: (top, bottom) tuple for FVG shading
        ob_zone: (top, bottom) tuple for OB shading

    Returns:
        PNG image bytes, or None if rendering unavailable/fails.
    """
    if not HAS_MPL or not candles or len(candles) < 10:
        return None

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        from matplotlib.patches import Rectangle
    except Exception:
        return None

    try:
        fig, ax = plt.subplots(figsize=(10, 6))
        fig.patch.set_facecolor('#1a1a2e')
        ax.set_facecolor('#16213e')

        times = []
        for c in candles[-60:]:
            t = c.get('time')
            if isinstance(t, (int, float)):
                from datetime import datetime, timezone
                times.append(datetime.fromtimestamp(t, tz=timezone.utc))
            elif isinstance(t, str):
                from datetime import datetime
                try:
                    times.append(datetime.fromisoformat(t.replace('Z', '+00:00')))
                except Exception:
                    times.append(datetime.now())
            else:
                times.append(datetime.now())

        ohlc = candles[-len(times):]

        width = max((times[-1] - times[0]).total_seconds() / (len(times) * 2), 3600) if len(times) > 1 else 3600
        width_days = width / 86400

        for i, (t, c) in enumerate(zip(times, ohlc)):
            o, h, l, cl = c.get('open', c.get('close', 0)), c.get('high', 0), c.get('low', 0), c.get('close', 0)
            color = '#00ff88' if cl >= o else '#ff4444'
            ax.plot([t, t], [l, h], color=color, linewidth=0.8)
            if cl >= o:
                rect = Rectangle((t - width_days * 0.4, o), width_days * 0.8, cl - o or 0.01,
                                 facecolor=color, edgecolor=color, linewidth=0.5)
            else:
                rect = Rectangle((t - width_days * 0.4, cl), width_days * 0.8, o - cl or 0.01,
                                 facecolor=color, edgecolor=color, linewidth=0.5)
            ax.add_patch(rect)

        # FVG zone
        if fvg_zone:
            top, bottom = max(fvg_zone), min(fvg_zone)
            ax.axhspan(bottom, top, alpha=0.15, color='#ffd700', zorder=2)
            ax.annotate('FVG', xy=(times[-1], (top + bottom) / 2),
                        color='#ffd700', fontsize=8, fontweight='bold',
                        va='center', ha='left')

        # OB zone
        if ob_zone:
            top, bottom = max(ob_zone), min(ob_zone)
            ax.axhspan(bottom, top, alpha=0.12, color='#00bfff', zorder=2)
            ax.annotate('OB', xy=(times[-1], (top + bottom) / 2),
                        color='#00bfff', fontsize=8, fontweight='bold',
                        va='center', ha='left')

        # Entry / SL / TP lines
        if entry_price:
            ax.axhline(entry_price, color='#00ff88', linewidth=1.2, linestyle='--', alpha=0.8)
            ax.annotate(f'Entry {entry_price}', xy=(times[-1], entry_price),
                        color='#00ff88', fontsize=7, va='bottom')

        if stop_loss:
            ax.axhline(stop_loss, color='#ff4444', linewidth=1, linestyle=':', alpha=0.7)
            ax.annotate(f'SL {stop_loss}', xy=(times[-1], stop_loss),
                        color='#ff4444', fontsize=7, va='top')

        if take_profit:
            ax.axhline(take_profit, color='#00ff88', linewidth=1, linestyle=':', alpha=0.7)
            ax.annotate(f'TP {take_profit}', xy=(times[-1], take_profit),
                        color='#00ff88', fontsize=7, va='bottom')

        # Formatting
        ax.set_title(f'{symbol} {tf}  |  {direction}  |  Score: {score}/100',
                     color='#e0e0e0', fontsize=13, fontweight='bold', pad=12)
        ax.tick_params(colors='#888888', labelsize=8)
        ax.spines['bottom'].set_color('#333344')
        ax.spines['top'].set_color('#333344')
        ax.spines['left'].set_color('#333344')
        ax.spines['right'].set_color('#333344')
        ax.grid(True, alpha=0.1, color='#444466')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        fig.autofmt_xdate()

        # Price labels on right
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:.2f}'))

        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=100, bbox_inches='tight',
                    facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    except Exception as e:
        log.warning(f"Chart render failed: {e}")
        try:
            plt.close('all')
        except Exception:
            pass
        return None


def render_structure_chart(symbol: str, tf: str, levels: List[Dict],
                            current_price: float) -> Optional[bytes]:
    """Render institutional structure level map as chart."""
    if not HAS_MPL or not levels:
        return None

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except Exception:
        return None

    try:
        fig, ax = plt.subplots(figsize=(8, 5))
        fig.patch.set_facecolor('#1a1a2e')
        ax.set_facecolor('#16213e')

        y_pos = 0
        for lvl in levels[::-1]:
            ltype = lvl.get('type', '')
            zone_str = lvl.get('zone', str(lvl.get('price', '')))
            state = lvl.get('state', '')

            try:
                parts = zone_str.split(' - ')
                if len(parts) == 2:
                    low, high = float(parts[0]), float(parts[1])
                else:
                    low = float(parts[0])
                    high = low + 0.5
            except (ValueError, IndexError):
                y_pos += 1
                continue

            color = '#ffd700' if 'FVG' in ltype else '#00bfff' if 'OB' in ltype else '#888888'
            alpha = 0.2 if 'FILLED' in state or 'MITIGATED' in state else 0.4

            ax.barh(y_pos, high - low, left=low, height=0.6, color=color, alpha=alpha)
            ax.text(low, y_pos, f' {ltype}', color='#e0e0e0', fontsize=7, va='center')
            y_pos += 1

        if current_price:
            ax.axvline(current_price, color='#ff4444', linewidth=1.5, linestyle='--', alpha=0.7)
            ax.annotate(f'Price {current_price}', xy=(current_price, y_pos - 0.5),
                        color='#ff4444', fontsize=8, va='bottom')

        ax.set_title(f'{symbol} {tf} \u2014 Institutional Levels',
                     color='#e0e0e0', fontsize=12, fontweight='bold')
        ax.tick_params(colors='#888888', labelsize=8)
        ax.set_yticks([])
        ax.spines['bottom'].set_color('#333344')
        ax.spines['top'].set_color('#333344')
        ax.spines['left'].set_color('#333344')
        ax.spines['right'].set_color('#333344')
        ax.grid(True, axis='x', alpha=0.1, color='#444466')

        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=100, bbox_inches='tight',
                    facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    except Exception as e:
        log.warning(f"Structure chart render failed: {e}")
        try:
            plt.close('all')
        except Exception:
            pass
        return None
