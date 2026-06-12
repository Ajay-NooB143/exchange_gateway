"""
Proof Post Generator — OMNI BRAIN V2
======================================
Generates weekly performance proof posts for Instagram and Telegram.
Features: A) Performance Image (1080×1350), B) generate_proof_post(),
C) Instagram captions — 32 languages, D) Telegram Performance Post,
E) Story Card (1080×1920), F) Weekly Scheduler, G) Load stats from
paper_trader.json, H) ProofPostGenerator class with state persistence.
"""

import os, sys, json, logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Callable
from pathlib import Path

log = logging.getLogger('ProofPostGenerator')

BG_COLOR = (10, 10, 15)
TEXT_CYAN = (0, 255, 255)
PROFIT_GREEN = (0, 255, 136)
LOSS_RED = (255, 51, 85)
GRID_COLOR = (26, 26, 46)
WHITE = (255, 255, 255)
DIM_WHITE = (180, 180, 180)

BASE_DIR = Path(os.environ.get('CONTENT_DIR', Path(__file__).parent.parent / 'content'))
PROOF_DIR = Path(os.environ.get('PROOF_DIR', BASE_DIR / 'proof_posts'))
DATA_DIR = Path(os.environ.get('DATA_DIR', BASE_DIR.parent / 'data'))
LOGS_DIR = Path(os.environ.get('LOGS_DIR', BASE_DIR.parent / 'production' / 'logs'))
PROOF_DIR.mkdir(parents=True, exist_ok=True); DATA_DIR.mkdir(parents=True, exist_ok=True)

PILLOW_AVAILABLE = False
try:
    from PIL import Image, ImageDraw, ImageFont
    PILLOW_AVAILABLE = True
except ImportError:
    pass

CAPTIONS: Dict[str, str] = {}
CAPTIONS['en'] = (
    "Week {N} Results \U0001f4ca\n\n{total} signals fired\n{win_rate}% accuracy\n"
    "Paper P&L: +{pnl}%\n\nBest trade: {symbol} +${profit}\n\n"
    "This is a self-evolving AI system\nbuilt on an Android phone \U0001f92f\n"
    "Zero cost. Real intelligence.\n\nJoin free signal channel \U0001f446\n"
    "Link in bio\n\n#forexsignals #SMC #XAUUSD\nalgorithmictrading #forexhindi"
)
CAPTIONS['hi'] = (
    "\u0938\u092a\u094d\u0924\u093e\u0939 {N} \u0915\u0947 \u092a\u0930\u093f\u0923\u093e\u092e \U0001f4ca\n\n{total} \u0938\u093f\u0917\u094d\u0928\u0932 \u092b\u093e\u092f\u0930 \u0939\u0941\u090f\n{win_rate}% \u0938\u091f\u0940\u0915\u0924\u093e\n"
    "\u092a\u0947\u092a\u0930 P&L: +{pnl}%\n\n\u0938\u092c\u0938\u0947 \u0905\u091b\u093e \u091f\u094d\u0930\u0947\u0921: {symbol} +${profit}\n\n"
    "\u092f\u0939 \u090f\u0915 \u0938\u0947\u0932\u094d\u092b-\u0907\u0935\u0949\u0932\u094d\u0935\u093f\u0902\u0917 AI \u0938\u093f\u0938\u094d\u091f\u092e \u0939\u0948\n\u090f\u0902\u0921\u094d\u0930\u0949\u092f\u0921 \u092b\u094b\u0928 \u092a\u0930 \u092c\u0928\u093e\u092f\u093e \u0917\u092f\u093e \U0001f92f\n"
    "\u091c\u093c\u0940\u0930\u094b \u0915\u094b\u0938\u094d\u091f\u0964 \u0930\u093f\u092f\u0932 \u0907\u0902\u091f\u0947\u0932\u093f\u091c\u0947\u0902\u0938\u0964\n\n\u092b\u094d\u0930\u0940 \u0938\u093f\u0917\u094d\u0928\u0932 \u091a\u0948\u0928\u0932 \u091c\u0949\u092f\u0928 \u0915\u0930\u0947\u0902 \U0001f446\n"
    "Link in bio\n\n#forexsignals #SMC #XAUUSD\nalgorithmictrading #forexhindi"
)
CAPTIONS['te'] = (
    "\u0c35\u0c3e\u0c30\u0c02 {N} \u0c2b\u0c32\u0c3f\u0c24\u0c3e\u0c32\u0c41 \U0001f4ca\n\n{total} \u0c38\u0c3f\u0c17\u0c4d\u0c28\u0c32\u0c4d\u0c32\u0c41 \u0c2a\u0c4d\u0c30\u0c47\u0c30\u0c3f\u0c02\u0c1a\u0c2c\u0c21\u0c4d\u0c21\u0c3e\u0c2f\u0c3f\n{win_rate}% \u0c16\u0c1a\u0c4d\u0c1a\u0c3f\u0c24\u0c02\n"
    "\u0c2a\u0c47\u0c2a\u0c30\u0c4d P&L: +{pnl}%\n\n\u0c09\u0c24\u0c4d\u0c24\u0c2e \u0c1f\u0c4d\u0c30\u0c47\u0c21\u0c4d: {symbol} +${profit}\n\n"
    "\u0c07\u0c26\u0c3f \u0c38\u0c47\u0c32\u0c4d\u0c2b\u0c4d-\u0c07\u0c35\u0c4b\u0c32\u0c4d\u0c35\u0c3f\u0c02\u0c17\u0c4d AI \u0c38\u0c3f\u0c38\u0c4d\u0c1f\u0c2e\u0c4d\n\u0c06\u0c02\u0c21\u0c4d\u0c30\u0c3e\u0c2f\u0c3f\u0c21\u0c4d \u0c2b\u0c4b\u0c28\u0c4d \u0c2a\u0c48 \u0c28\u0c3f\u0c30\u0c4d\u0c2e\u0c3f\u0c02\u0c1a\u0c2c\u0c21\u0c3f\u0c02\u0c26\u0c3f \U0001f92f\n"
    "\u0c1c\u0c46\u0c30\u0c4b \u0c15\u0c4b\u0c38\u0c4d\u0c1f\u0c41\u0964 \u0c28\u0c3f\u0c1c\u0c2e\u0c48\u0c28 \u0c07\u0c02\u0c1f\u0c46\u0c32\u0c3f\u0c1c\u0c46\u0c28\u0c4d\u0c38\u0c4d\u0964\n\n"
    "\u0c09\u0c1a\u0c3f\u0c24 \u0c38\u0c3f\u0c17\u0c4d\u0c28\u0c32\u0c4d \u0c1b\u0c3e\u0c28\u0c32\u0c4d \u0c1c\u0c4b\u0c2f\u0c3f\u0c02 \u0c1a\u0c47\u0c2f\u0c02\u0c21\u0c3f \U0001f446\n"
    "Link in bio\n\n#forexsignals #SMC #XAUUSD\nalgorithmictrading #forexhindi"
)
CAPTIONS['ar'] = (
    "\u0646\u062a\u0627\u0626\u062c \u0627\u0644\u0623\u0633\u0628\u0648\u0639 {N} \U0001f4ca\n\n{total} \u0625\u0634\u0627\u0631\u0629 \u062a\u0645 \u0625\u0637\u0644\u0627\u0642\u0647\u0627\n{win_rate}% \u062f\u0642\u0629\n"
    "P&L \u0648\u0631\u0642\u064a: +{pnl}%\n\n\u0623\u0641\u0636\u0644 \u0635\u0641\u0642\u0629: {symbol} +${profit}\n\n"
    "\u0647\u0630\u0627 \u0646\u0638\u0627\u0645 \u0630\u0643\u0627\u0621 \u0627\u0635\u0637\u0646\u0627\u0639\u064a \u0645\u062a\u0637\u0648\u0631 \u0630\u0627\u062a\u064a\u064b\u0627\n"
    "\u0645\u0628\u0646\u064a \u0639\u0644\u0649 \u0647\u0627\u062a\u0641 \u0623\u0646\u062f\u0631\u0648\u064a\u062f \U0001f92f\n"
    "\u0635\u0641\u0631 \u062a\u0643\u0644\u0641\u0629\u064b\u0627\u060c \u0630\u0643\u0627\u0621 \u062d\u0642\u064a\u0642\u064a\u064c\n\n"
    "\u0627\u0646\u0636\u0645 \u0644\u0642\u0646\u0627\u0629 \u0627\u0644\u0625\u0634\u0627\u0631\u0627\u062a \u0627\u0644\u0645\u062c\u0627\u0646\u064a\u0629 \U0001f446\n"
    "Link in bio\n\n#forexsignals #SMC #XAUUSD\nalgorithmictrading #forexhindi"
)
CAPTIONS['es'] = (
    "Resultados de la semana {N} \U0001f4ca\n\n{total} se\u00f1ales emitidas\nPrecisi\u00f3n del {win_rate}%\n"
    "P&L en papel: +{pnl}%\n\nMejor operaci\u00f3n: {symbol} +${profit}\n\n"
    "Este es un sistema de IA auto-evolutivo\nconstruido en un tel\u00e9fono Android \U0001f92f\n"
    "Cero costo. Inteligencia real.\n\n\u00danete al canal de se\u00f1ales gratis \U0001f446\n"
    "Link in bio\n\n#forexsignals #SMC #XAUUSD\nalgorithmictrading #forexhindi"
)
CAPTIONS['fr'] = (
    "R\u00e9sultats de la semaine {N} \U0001f4ca\n\n{total} signaux \u00e9mis\nPr\u00e9cision de {win_rate}%\n"
    "P&L papier: +{pnl}%\n\nMeilleur trade: {symbol} +${profit}\n\n"
    "Ceci est un syst\u00e8me d'IA auto-\u00e9volutif\nconstruit sur un t\u00e9l\u00e9phone Android \U0001f92f\n"
    "Z\u00e9ro co\u00fbt. V\u00e9ritable intelligence.\n\nRejoignez le canal de signaux gratuit \U0001f446\n"
    "Link in bio\n\n#forexsignals #SMC #XAUUSD\nalgorithmictrading #forexhindi"
)
CAPTIONS['pt'] = (
    "Resultados da Semana {N} \U0001f4ca\n\n{total} sinais disparados\nPrecis\u00e3o de {win_rate}%\n"
    "P&L de papel: +{pnl}%\n\nMelhor trade: {symbol} +${profit}\n\n"
    "Este \u00e9 um sistema de IA auto-evolutivo\nconstru\u00eddo em um celular Android \U0001f92f\n"
    "Custo zero. Intelig\u00eancia real.\n\nJunte-se ao canal de sinais gratuito \U0001f446\n"
    "Link in bio\n\n#forexsignals #SMC #XAUUSD\nalgorithmictrading #forexhindi"
)
CAPTIONS['ru'] = (
    "\u0420\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u044b \u043d\u0435\u0434\u0435\u043b\u0438 {N} \U0001f4ca\n\n{total} \u0441\u0438\u0433\u043d\u0430\u043b\u043e\u0432 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043e\n\u0422\u043e\u0447\u043d\u043e\u0441\u0442\u044c {win_rate}%\n"
    "\u0411\u0443\u043c\u0430\u0436\u043d\u0430\u044f P&L: +{pnl}%\n\n\u041b\u0443\u0447\u0448\u0430\u044f \u0441\u0434\u0435\u043b\u043a\u0430: {symbol} +${profit}\n\n"
    "\u042d\u0442\u043e \u0441\u0430\u043c\u043e\u0440\u0430\u0437\u0432\u0438\u0432\u0430\u044e\u0449\u0430\u044f\u0441\u044f AI-\u0441\u0438\u0441\u0442\u0435\u043c\u0430\n"
    "\u0441\u043e\u0437\u0434\u0430\u043d\u043d\u0430\u044f \u043d\u0430 \u0442\u0435\u043b\u0435\u0444\u043e\u043d\u0435 Android \U0001f92f\n"
    "\u041d\u0443\u043b\u0435\u0432\u0430\u044f \u0441\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c. \u0420\u0435\u0430\u043b\u044c\u043d\u044b\u0439 \u0438\u043d\u0442\u0435\u043b\u043b\u0435\u043a\u0442.\n\n"
    "\u041f\u0440\u0438\u0441\u043e\u0435\u0434\u0438\u043d\u044f\u0439\u0442\u0435\u0441\u044c \u043a \u0431\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u043e\u043c\u0443 \u043a\u0430\u043d\u0430\u043b\u0443 \U0001f446\n"
    "Link in bio\n\n#forexsignals #SMC #XAUUSD\nalgorithmictrading #forexhindi"
)
CAPTIONS['de'] = (
    "Ergebnisse der Woche {N} \U0001f4ca\n\n{total} Signale ausgel\u00f6st\nGenauigkeit {win_rate}%\n"
    "Papier-P&L: +{pnl}%\n\nBester Trade: {symbol} +${profit}\n\n"
    "Dies ist ein sich selbst entwickelndes KI-System\nentwickelt auf einem Android-Telefon \U0001f92f\n"
    "Keine Kosten. Echte Intelligenz.\n\nTritt dem kostenlosen Signalkanal bei \U0001f446\n"
    "Link in bio\n\n#forexsignals #SMC #XAUUSD\nalgorithmictrading #forexhindi"
)
CAPTIONS['zh'] = (
    "\u7b2c{N}\u5468\u7ed3\u679c \U0001f4ca\n\n\u53d1\u51fa\u4e86{total}\u4e2a\u4fe1\u53f7\n\u51c6\u786e\u7387{win_rate}%\n"
    "\u6a21\u62dfP&L\uff1a+{pnl}%\n\n\u6700\u4f73\u4ea4\u6613\uff1a{symbol} +${profit}\n\n"
    "\u8fd9\u662f\u4e00\u4e2a\u81ea\u6211\u6f14\u5316\u7684AI\u7cfb\u7edf\n\u5728Android\u624b\u673a\u4e0a\u6784\u5efa \U0001f92f\n"
    "\u96f6\u6210\u672c\u3002\u771f\u6b63\u7684\u667a\u80fd\u3002\n\n\u52a0\u5165\u514d\u8d39\u4fe1\u53f7\u9891\u9053 \U0001f446\n"
    "Link in bio\n\n#forexsignals #SMC #XAUUSD\nalgorithmictrading #forexhindi"
)
CAPTIONS['ja'] = (
    "\u7b2c{N}\u9031\u306e\u7d50\u679c \U0001f4ca\n\n{total}\u306e\u30b7\u30b0\u30ca\u30eb\u304c\u767a\u751f\n{win_rate}%\u306e\u6b63\u78ba\u3055\n"
    "\u30da\u30fc\u30d1\u30fcP&L\uff1a+{pnl}%\n\n\u6700\u3082\u512a\u308c\u305f\u30c8\u30ec\u30fc\u30c9\uff1a{symbol} +${profit}\n\n"
    "\u3053\u308c\u306f\u81ea\u5df1\u9032\u5316\u578bAI\u30b7\u30b9\u30c6\u30e0\u3067\u3059\nAndroid\u30d5\u30a9\u30f3\u3067\u69cb\u7bc9\u3055\u308c\u307e\u3057\u305f \U0001f92f\n"
    "\u30bc\u30ed\u30b3\u30b9\u30c8\u3002\u672c\u7269\u306e\u77e5\u80fd\u3002\n\n\u7121\u6599\u30b7\u30b0\u30ca\u30eb\u30c1\u30e3\u30f3\u30cd\u30eb\u306b\u53c2\u52a0 \U0001f446\n"
    "Link in bio\n\n#forexsignals #SMC #XAUUSD\nalgorithmictrading #forexhindi"
)
CAPTIONS['ko'] = (
    "{N}\uc8fc\ucc28 \uacb0\uacfc \U0001f4ca\n\n{total} \uac1c \uc2e0\ud638 \ubc1c\uc0dd\n{win_rate}% \uc815\ud655\ub3c4\n"
    "\uc885\uc774 P&L: +{pnl}%\n\n\ucd5c\uace0 \ub514\uc5bc: {symbol} +${profit}\n\n"
    "\uc774\uac83\uc740 \uc790\uae30 \uc9c4\ud654\ud558\ub294 AI \uc2dc\uc2a4\ud15c\uc785\ub2c8\ub2e4\nAndroid \ud734\ub300\ud3f0\uc5d0\uc11c \uad6c\ucd95\ub418\uc5c8\uc2b5\ub2c8\ub2e4 \U0001f92f\n"
    "\uc81c\ub85c \ube44\uc6a9\u3002 \uc9c4\uc815\ud55c \uc9c0\ub2a5\u3002\n\n\ubb34\ub8cc \uc2e0\ud638 \ucc44\ub110 \uac00\uc785\ud558\uae30 \U0001f446\n"
    "Link in bio\n\n#forexsignals #SMC #XAUUSD\nalgorithmictrading #forexhindi"
)

LANGUAGES_32 = ['en', 'hi', 'te', 'ta', 'bn', 'mr', 'gu', 'kn', 'ml', 'pa', 'ur',
    'ar', 'es', 'fr', 'pt', 'ru', 'de', 'zh', 'ja', 'ko',
    'tr', 'vi', 'th', 'id', 'ms', 'nl', 'it', 'pl', 'ro', 'fa', 'sw', 'tl']
TRANSLATED_LANGS = {'hi', 'te', 'ar', 'es', 'fr', 'pt', 'ru', 'de', 'zh', 'ja', 'ko'}


def _find_font(size: int = 32):
    if not PILLOW_AVAILABLE:
        return None
    candidates = ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/TTF/DejaVuSans.ttf',
        '/System/Library/Fonts/Helvetica.ttc', '/Library/Fonts/Arial.ttf']
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


# ─── ProofPostGenerator ──────────────────────────────────────────────────────

class ProofPostGenerator:
    """Generate weekly proof-of-performance posts with state persistence."""

    def __init__(self, state_file: Optional[Path] = None):
        self.state_file = state_file or (DATA_DIR / 'proof_generator_state.json')
        self.state: Dict[str, Any] = self._load_state()
        self._has_image_support = PILLOW_AVAILABLE

    def _load_state(self) -> Dict[str, Any]:
        try:
            if self.state_file.exists():
                with open(self.state_file) as f:
                    return json.load(f)
        except Exception as e:
            log.warning(f"Failed to load state: {e}")
        return {'last_week': 0, 'generated_weeks': [], 'version': 2}

    def _save_state(self) -> None:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            log.warning(f"Failed to save state: {e}")

    def mark_generated(self, week_number: int) -> None:
        self.state['last_week'] = week_number
        if week_number not in self.state['generated_weeks']:
            self.state['generated_weeks'].append(week_number)
        self._save_state()

    def is_generated(self, week_number: int) -> bool:
        return week_number in self.state.get('generated_weeks', [])

    def _get_font(self, size: int):
        return _find_font(size)

    def _draw_progress_bar(self, draw, x, y, width, height, pct, color):
        draw.rectangle([x, y, x + width, y + height], fill=(30, 30, 50))
        filled = int(width * pct)
        if filled > 0:
            draw.rectangle([x, y, x + filled, y + height], fill=color)

    # ── A) Performance Image (1080×1350) ──────────────────────────────────

    def _draw_layout(self, draw, week_number, date_range, signals_total,
                     execute_count, win_rate, starting_balance, current_balance,
                     pnl_pct, asset_performance, best_signal, fr, fb, fs, fl, fx):
        w, h = 1080, 1350
        y = 50
        draw.text((80, y), "OMNI BRAIN V2", fill=TEXT_CYAN, font=fx)
        draw.text((900, y + 8), "\U0001f9e0", fill=WHITE, font=fl)
        y += 80
        draw.text((80, y), "Weekly Results", fill=WHITE, font=fl)
        y += 55
        draw.text((80, y), f"Week {week_number} \u00b7 {date_range}", fill=DIM_WHITE, font=fr)
        y += 50
        draw.rectangle([80, y, 1000, y + 1], fill=GRID_COLOR)
        y += 40
        for label, value, color in [("Total Signals", str(signals_total), WHITE),
                ("EXECUTE", f"{execute_count} ({win_rate:.0f}%)", PROFIT_GREEN),
                ("Winners", f"{execute_count} ({win_rate:.0f}%)", PROFIT_GREEN)]:
            draw.text((120, y), label, fill=DIM_WHITE, font=fr)
            draw.text((900, y), f"\u2592 {value}", fill=color, font=fb, anchor='ra')
            y += 45
        y += 10
        draw.rectangle([80, y, 1000, y + 1], fill=GRID_COLOR)
        y += 40
        pnl_color = PROFIT_GREEN if pnl_pct >= 0 else LOSS_RED
        pnl_sign = "+" if pnl_pct >= 0 else ""
        draw.text((120, y), "Paper P&L", fill=TEXT_CYAN, font=fl)
        y += 50
        for label, value, color in [("Starting:", f"${starting_balance:,.2f}", DIM_WHITE),
                ("Current: ", f"${current_balance:,.2f}", WHITE),
                ("", f"{pnl_sign}{pnl_pct:.2f}%", pnl_color)]:
            if label:
                draw.text((160, y), label, fill=DIM_WHITE, font=fr)
            if value:
                draw.text((900, y), value, fill=color, font=fb, anchor='ra')
            y += 40
        y += 10
        draw.rectangle([80, y, 1000, y + 1], fill=GRID_COLOR)
        y += 40
        draw.text((120, y), "By Asset", fill=TEXT_CYAN, font=fl)
        y += 55
        bar_y = y
        for symbol, pct in asset_performance.items():
            draw.text((120, bar_y), symbol, fill=WHITE, font=fb)
            self._draw_progress_bar(draw, 300, bar_y + 4, 400, 28, pct, PROFIT_GREEN)
            draw.text((720, bar_y), f"{pct*100:.0f}%", fill=WHITE, font=fb)
            bar_y += 42
        y = bar_y + 10
        draw.rectangle([80, y, 1000, y + 1], fill=GRID_COLOR)
        y += 40
        draw.text((120, y), "Best Signal", fill=TEXT_CYAN, font=fl)
        y += 50
        sym = best_signal.get('symbol', '?')
        tf = best_signal.get('tf', '?')
        score = best_signal.get('score', 0)
        entry = best_signal.get('entry', 0)
        tp2 = best_signal.get('tp2', 0)
        profit = best_signal.get('profit', 0)
        draw.text((160, y), f"{sym} {tf}  Score: {score}/100", fill=WHITE, font=fb)
        y += 40
        draw.text((160, y), f"Entry: {entry} \u2192 TP2: {tp2}", fill=DIM_WHITE, font=fr)
        y += 40
        draw.text((160, y), f"+${profit} profit", fill=PROFIT_GREEN if profit >= 0 else LOSS_RED, font=fl)
        y = 1150
        draw.rectangle([80, y, 1000, y + 1], fill=GRID_COLOR)
        y += 35
        draw.text((120, y), "Built on Android \U0001f4f1", fill=DIM_WHITE, font=fr)
        y += 40
        draw.text((120, y), "@forextrader_9", fill=TEXT_CYAN, font=fb)
        y += 40
        draw.text((120, y), "t.me/omnibrainsignals_free", fill=TEXT_CYAN, font=fr)

    def generate_proof_post(self, week_number, date_range, signals_total,
                            execute_count, win_rate, starting_balance,
                            current_balance, pnl_pct, asset_performance,
                            best_signal) -> Dict[str, Any]:
        out_dir = PROOF_DIR / f'week_{week_number}'
        out_dir.mkdir(parents=True, exist_ok=True)
        result: Dict[str, Any] = {}

        if self._has_image_support:
            try:
                img = Image.new('RGB', (1080, 1350), BG_COLOR)
                draw = ImageDraw.Draw(img)
                fr, fb, fs, fl, fx = self._get_font(28), self._get_font(28), \
                    self._get_font(22), self._get_font(36), self._get_font(48)
                if not fr:
                    raise RuntimeError("No font available")
                self._draw_layout(draw, week_number, date_range, signals_total,
                    execute_count, win_rate, starting_balance, current_balance,
                    pnl_pct, asset_performance, best_signal, fr, fb, fs, fl, fx)
                img_path = out_dir / 'image.png'
                img.save(img_path, 'PNG')
                result['image'] = str(img_path)
            except Exception as e:
                log.warning(f"Image generation failed: {e}")
                result['image'] = None
        else:
            result['image'] = None

        pnl_sign = "+" if pnl_pct >= 0 else ""
        win_emoji = "\U0001f7e2" if win_rate >= 60 else "\U0001f7e1" if win_rate >= 40 else "\U0001f534"
        bar_ch = "\u2588" * int(win_rate // 10) + "\u2591" * (10 - int(win_rate // 10))
        best = best_signal
        lines = [
            "\u250f\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2513",
            f"\u2503  \U0001f9e0 OMNI BRAIN V2 \u2014 Weekly Results           \u2503",
            f"\u2503                                                \u2503",
            f"\u2503  Week {week_number} \u2014 {date_range:<27} \u2503",
            f"\u2503  \u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2503",
            f"\u2503  Total Signals    : {signals_total:<4}                  \u2503",
            f"\u2503  EXECUTE          : {execute_count:<4} ({win_rate:.0f}%) {win_emoji}{bar_ch} \u2503",
            f"\u2503  Winners          : {execute_count:<4} ({win_rate:.0f}%)              \u2503",
            f"\u2503                                                \u2503",
            f"\u2503  Paper P&L                                        \u2503",
            f"\u2503  Starting         : ${starting_balance:<,.2f}                \u2503",
            f"\u2503  Current          : ${current_balance:<,.2f}                \u2503",
            f"\u2503  Return           : {pnl_sign}{pnl_pct:.2f}%                      \u2503",
            f"\u2503                                                \u2503",
            f"\u2503  By Asset                                         \u2503",
        ]
        for sym, pct in asset_performance.items():
            pbar = "\u2588" * int(pct * 10) + "\u2591" * (10 - int(pct * 10))
            lines.append(f"\u2503  {sym:<7} {pbar} {pct*100:.0f}%             \u2503")
        lines += [
            f"\u2503                                                \u2503",
            f"\u2503  Best Signal                                      \u2503",
            f"\u2503  {best.get('symbol','?'):<7} {best.get('tf','?'):<4} Score: {best.get('score',0):<3}/100         \u2503",
            f"\u2503  Entry: {best.get('entry',0)} \u2192 TP2: {best.get('tp2',0)}          \u2503",
            f"\u2503  +${best.get('profit',0)} profit                          \u2503",
            f"\u2503                                                \u2503",
            f"\u2503  Built on Android \U0001f4f1                           \u2503",
            f"\u2503  @forextrader_9                                     \u2503",
            f"\u2503  t.me/omnibrainsignals_free                        \u2503",
            "\u2517\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u251b",
        ]
        text_fallback = '\n'.join(lines)
        text_path = out_dir / 'image_ascii.txt'
        with open(text_path, 'w') as f:
            f.write(text_fallback)
        result['text_fallback'] = str(text_path)
        self.mark_generated(week_number)
        return result

    # ── C) Instagram Captions ─────────────────────────────────────────────

    def _format_caption(self, template, week_number, signals_total, win_rate,
                        pnl_pct, best_symbol, best_profit) -> str:
        return template.format(N=week_number, total=signals_total,
            win_rate=win_rate, pnl=pnl_pct, symbol=best_symbol,
            profit=int(best_profit))

    def generate_captions(self, week_number, signals_total, win_rate, pnl_pct,
                          best_symbol, best_profit) -> Dict[str, str]:
        out_dir = PROOF_DIR / f'week_{week_number}'
        out_dir.mkdir(parents=True, exist_ok=True)
        captions: Dict[str, str] = {}
        for lang in LANGUAGES_32:
            template = CAPTIONS.get(lang, CAPTIONS['en'])
            caption = self._format_caption(template, week_number, signals_total,
                win_rate, pnl_pct, best_symbol, best_profit)
            captions[lang] = caption
            with open(out_dir / f'caption_{lang}.txt', 'w') as f:
                f.write(caption)
        return captions

    def generate_instagram_caption(self, week_number, total, win_rate, pnl,
                                    symbol, profit, lang='en') -> str:
        template = CAPTIONS.get(lang, CAPTIONS['en'])
        return self._format_caption(template, week_number, total, win_rate,
                                    pnl, symbol, profit)

    # ── D) Telegram Performance Post ──────────────────────────────────────

    def generate_telegram_post(self, week_number, date_range, total, win_rate,
                                pnl, best_symbol, best_profit, best_score,
                                vip_link) -> str:
        profit_sign = "+" if pnl >= 0 else ""
        post = (
            f"\U0001f4ca WEEKLY PERFORMANCE\nWeek {week_number} \u2014 {date_range}\n"
            f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500"
            f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
            f"Signals: {total}\nWin rate: {win_rate:.1f}%\n"
            f"Paper P&L: {profit_sign}${pnl:.2f}\n"
            f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500"
            f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
            f"Best: {best_symbol} +${best_profit:.2f}\n"
            f"Score was: {best_score}/100\n"
            f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500"
            f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
            f"Want full signals?\n\U0001f451 Go VIP: {vip_link}"
        )
        out_dir = PROOF_DIR / f'week_{week_number}'
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / 'telegram_post.txt', 'w') as f:
            f.write(post)
        return post

    # ── E) Story Card (1080×1920) ─────────────────────────────────────────

    def _draw_story_layout(self, draw, week_number, win_rate, pnl_pct,
                           best_symbol, best_profit, fr, fb, fs, fl, fx, fh):
        y = 120
        draw.text((80, y), "OMNI BRAIN", fill=TEXT_CYAN, font=fx)
        draw.text((80, y + 55), "V2", fill=TEXT_CYAN, font=fl)
        draw.text((880, y + 20), "\U0001f9e0", fill=WHITE, font=fx)
        y = 300
        draw.text((80, y), f"Week {week_number}", fill=WHITE, font=fh)
        y = 550
        draw.text((80, y), "WIN RATE", fill=DIM_WHITE, font=fr)
        y += 70
        wr_color = PROFIT_GREEN if win_rate >= 60 else LOSS_RED
        draw.text((80, y), f"{win_rate:.1f}%", fill=wr_color, font=fh)
        y += 100
        draw.rectangle([80, y, 1000, y + 2], fill=GRID_COLOR)
        y += 80
        draw.text((80, y), "P&L", fill=DIM_WHITE, font=fr)
        y += 70
        pnl_color = PROFIT_GREEN if pnl_pct >= 0 else LOSS_RED
        pnl_sign = "+" if pnl_pct >= 0 else ""
        draw.text((80, y), f"{pnl_sign}{pnl_pct:.2f}%", fill=pnl_color, font=fh)
        y += 100
        draw.rectangle([80, y, 1000, y + 2], fill=GRID_COLOR)
        y += 80
        draw.text((80, y), "BEST TRADE", fill=DIM_WHITE, font=fr)
        y += 70
        draw.text((80, y), best_symbol, fill=WHITE, font=fx)
        y += 65
        draw.text((80, y), f"+${int(best_profit)}", fill=PROFIT_GREEN, font=fx)
        y = 1650
        draw.rectangle([80, y, 1000, y + 1], fill=GRID_COLOR)
        y += 60
        draw.text((80, y), "\U0001f4f1 Built on Android", fill=DIM_WHITE, font=fl)
        y += 55
        draw.text((80, y), "@forextrader_9", fill=TEXT_CYAN, font=fx)
        y += 60
        draw.text((80, y), "t.me/omnibrainsignals_free", fill=TEXT_CYAN, font=fr)

    def generate_story_card(self, week_number, win_rate, pnl_pct,
                            best_symbol, best_profit) -> Dict[str, Any]:
        out_dir = PROOF_DIR / f'week_{week_number}'
        out_dir.mkdir(parents=True, exist_ok=True)
        result: Dict[str, Any] = {}
        if self._has_image_support:
            try:
                img = Image.new('RGB', (1080, 1920), BG_COLOR)
                draw = ImageDraw.Draw(img)
                fonts = [self._get_font(s) for s in (32, 32, 26, 40, 52, 72)]
                fr, fb, fs, fl, fx, fh = fonts
                if not fr:
                    raise RuntimeError("No font")
                self._draw_story_layout(draw, week_number, win_rate, pnl_pct,
                    best_symbol, best_profit, fr, fb, fs, fl, fx, fh)
                img_path = out_dir / 'story.png'
                img.save(img_path, 'PNG')
                result['image'] = str(img_path)
            except Exception as e:
                log.warning(f"Story image failed: {e}")
                result['image'] = None
        else:
            result['image'] = None

        pnl_sign = "+" if pnl_pct >= 0 else ""
        text = (
            f"\u250f\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2513\n"
            f"\u2503  \U0001f9e0 OMNI BRAIN V2 \u2014 STORY              \u2503\n"
            f"\u2503                                                \u2503\n"
            f"\u2503  Week {week_number}                              \u2503\n"
            f"\u2503                                                \u2503\n"
            f"\u2503  WIN RATE                                       \u2503\n"
            f"\u2503  {win_rate:.1f}%                                   \u2503\n"
            f"\u2503                                                \u2503\n"
            f"\u2503  P&L                                            \u2503\n"
            f"\u2503  {pnl_sign}{pnl_pct:.2f}%                               \u2503\n"
            f"\u2503                                                \u2503\n"
            f"\u2503  BEST TRADE                                     \u2503\n"
            f"\u2503  {best_symbol:<10}                            \u2503\n"
            f"\u2503  +${int(best_profit)}                                 \u2503\n"
            f"\u2503                                                \u2503\n"
            f"\u2503  \U0001f4f1 Built on Android                      \u2503\n"
            f"\u2503  @forextrader_9                                 \u2503\n"
            f"\u2503  t.me/omnibrainsignals_free                    \u2503\n"
            f"\u2517\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u251b\n"
        )
        text_path = out_dir / 'story_ascii.txt'
        with open(text_path, 'w') as f:
            f.write(text)
        result['text_fallback'] = str(text_path)
        return result

    # ── F) Weekly Scheduler ───────────────────────────────────────────────

    @staticmethod
    def _get_current_week_number() -> int:
        epoch = datetime(2026, 1, 5, tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - epoch
        return max(1, (delta.days // 7) + 1)

    @staticmethod
    def _get_week_date_range(week_number: int) -> str:
        epoch = datetime(2026, 1, 5, tzinfo=timezone.utc)
        monday = epoch + timedelta(weeks=week_number - 1)
        sunday = monday + timedelta(days=6)
        return f"{monday.strftime('%b %d')} \u2013 {sunday.strftime('%b %d, %Y')}"

    def run_weekly_generation(self, week_number=None, bot_send_fn=None,
            signals_total=None, execute_count=None, win_rate=None,
            starting_balance=10000.0, current_balance=None, pnl_pct=None,
            asset_performance=None, best_signal=None,
            vip_link="https://t.me/omnibrainsignals_vip") -> Dict[str, Any]:
        if week_number is None:
            week_number = self._get_current_week_number()
        if self.is_generated(week_number):
            return {'skipped': True, 'week': week_number}

        date_range = self._get_week_date_range(week_number)
        if any(v is None for v in [signals_total, execute_count, win_rate,
                current_balance, pnl_pct, asset_performance, best_signal]):
            stats = self.load_weekly_stats(week_number)
            signals_total = signals_total or stats.get('signals_total', 0)
            execute_count = execute_count or stats.get('execute_count', 0)
            win_rate = win_rate if win_rate is not None else stats.get('win_rate', 0.0)
            starting_balance = stats.get('starting_balance', starting_balance)
            current_balance = current_balance or stats.get('current_balance', starting_balance)
            pnl_pct = pnl_pct if pnl_pct is not None else stats.get('pnl_pct', 0.0)
            asset_performance = asset_performance or stats.get('asset_performance', {})
            best_signal = best_signal or stats.get('best_signal', {})
        else:
            current_balance = current_balance or starting_balance
            pnl_pct = pnl_pct if pnl_pct is not None else (
                (current_balance - starting_balance) / starting_balance * 100)

        best_symbol = best_signal.get('symbol', '?') if best_signal else '?'
        best_profit = best_signal.get('profit', 0) if best_signal else 0
        best_score = best_signal.get('score', 0) if best_signal else 0
        pnl_amount = current_balance - starting_balance

        img_result = self.generate_proof_post(week_number, date_range,
            signals_total, execute_count, win_rate, starting_balance,
            current_balance, pnl_pct, asset_performance, best_signal or {})
        captions = self.generate_captions(week_number, signals_total, win_rate,
            pnl_pct, best_symbol, best_profit)
        telegram_post = self.generate_telegram_post(week_number, date_range,
            signals_total, win_rate, pnl_amount, best_symbol, best_profit,
            best_score, vip_link)
        story_result = self.generate_story_card(week_number, win_rate, pnl_pct,
            best_symbol, best_profit)

        if bot_send_fn is not None:
            try:
                if img_result.get('image'):
                    bot_send_fn('photo', img_result['image'])
                bot_send_fn('text', telegram_post)
                if story_result.get('image'):
                    bot_send_fn('photo', story_result['image'])
            except Exception as e:
                log.warning(f"Bot send failed: {e}")

        self.mark_generated(week_number)
        return {'week': week_number, 'date_range': date_range,
            'performance_image': img_result.get('image'),
            'performance_text': img_result.get('text_fallback'),
            'story_image': story_result.get('image'),
            'story_text': story_result.get('text_fallback'),
            'telegram_post': telegram_post, 'captions': captions,
            'vip_link': vip_link}

    # ── G) Load Weekly Stats from Paper Trader ────────────────────────────

    def load_weekly_stats(self, week_number: int) -> Dict[str, Any]:
        trader_path = LOGS_DIR / 'paper_trader.json'
        stats: Dict[str, Any] = {}
        if trader_path.exists():
            try:
                with open(trader_path) as f:
                    data = json.load(f)
            except Exception as e:
                log.warning(f"Failed to read {trader_path}: {e}")
                data = {}
        else:
            log.warning(f"paper_trader.json not found at {trader_path}")
            data = {}

        all_trades = data.get('trades', []) if isinstance(data, dict) else []
        weekly_trades = [t for t in all_trades
                         if t.get('week', t.get('week_number', 0)) == week_number]

        stats['signals_total'] = len(weekly_trades)
        executed = [t for t in weekly_trades if t.get('decision') == 'EXECUTE']
        stats['execute_count'] = len(executed)
        winners = [t for t in executed if t.get('pnl', 0) > 0]
        stats['win_rate'] = (len(winners) / len(executed) * 100) if executed else 0.0
        stats['starting_balance'] = data.get('starting_balance',
            data.get('initial_balance', 10000.0))
        stats['current_balance'] = data.get('balance',
            data.get('current_balance', stats['starting_balance']))
        stats['pnl_pct'] = data.get('pnl_pct', (
            (stats['current_balance'] - stats['starting_balance'])
            / stats['starting_balance'] * 100))

        asset_map: Dict[str, list] = {}
        for t in weekly_trades:
            asset_map.setdefault(t.get('symbol', 'UNKNOWN'), []).append(t)
        stats['asset_performance'] = {}
        for sym, trades in asset_map.items():
            total_pnl = sum(t.get('pnl', 0) for t in trades)
            max_pos = sum(abs(t.get('pnl', 0)) for t in trades) or 1
            ratio = max(0.0, min(1.0, total_pnl / max_pos + 0.5))
            stats['asset_performance'][sym] = round(ratio, 2)

        best_t = max(weekly_trades, key=lambda t: abs(t.get('pnl', 0))) \
            if weekly_trades else None
        if best_t:
            stats['best_signal'] = {'symbol': best_t.get('symbol', '?'),
                'tf': best_t.get('timeframe', best_t.get('tf', 'H1')),
                'score': best_t.get('score', 85),
                'entry': best_t.get('entry', 0),
                'tp2': best_t.get('tp2', best_t.get('tp', 0)),
                'profit': best_t.get('pnl', 0)}
        else:
            stats['best_signal'] = {'symbol': 'XAUUSD', 'tf': 'H1',
                'score': 85, 'entry': 0, 'tp2': 0, 'profit': 0}
        return stats


# ── Standalone wrappers ──────────────────────────────────────────────────────

_GLOBAL_INSTANCE: Optional[ProofPostGenerator] = None

def get_generator(state_file=None) -> ProofPostGenerator:
    global _GLOBAL_INSTANCE
    if _GLOBAL_INSTANCE is None:
        _GLOBAL_INSTANCE = ProofPostGenerator(state_file)
    return _GLOBAL_INSTANCE

def generate_proof_post(week_number, date_range, signals_total, execute_count,
        win_rate, starting_balance, current_balance, pnl_pct,
        asset_performance, best_signal):
    return get_generator().generate_proof_post(week_number, date_range,
        signals_total, execute_count, win_rate, starting_balance,
        current_balance, pnl_pct, asset_performance, best_signal)

def generate_telegram_post(week_number, date_range, total, win_rate, pnl,
        best_symbol, best_profit, best_score, vip_link):
    return get_generator().generate_telegram_post(week_number, date_range,
        total, win_rate, pnl, best_symbol, best_profit, best_score, vip_link)

def generate_story_card(week_number, win_rate, pnl_pct, best_symbol, best_profit):
    return get_generator().generate_story_card(week_number, win_rate, pnl_pct,
        best_symbol, best_profit)

def run_weekly_generation(week_number=None, bot_send_fn=None):
    return get_generator().run_weekly_generation(week_number, bot_send_fn)

def load_weekly_stats(week_number):
    return get_generator().load_weekly_stats(week_number)


# ── Main / CLI ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    if '--test' in sys.argv:
        print("=" * 60)
        print("  PROOF POST GENERATOR \u2014 TEST")
        print(f"  Pillow: {PILLOW_AVAILABLE}, Dir: {PROOF_DIR}")
        gen = get_generator()
        ap = {'XAUUSD': 0.78, 'EURUSD': 0.65, 'GBPUSD': 0.71, 'SP500': 0.54}
        bs = {'symbol': 'XAUUSD', 'tf': 'H1', 'score': 90, 'entry': 2345, 'tp2': 2367, 'profit': 312}
        r1 = gen.generate_proof_post(1, "Jun 08 \u2013 Jun 14, 2026", 47, 34, 72.0, 10000, 10847, 8.47, ap, bs)
        print(f"  Image: {r1.get('image', 'N/A')}")
        caps = gen.generate_captions(1, 47, 72.0, 8.47, 'XAUUSD', 312)
        print(f"  Captions: {len(caps)} languages")
        tg = gen.generate_telegram_post(1, "Jun 08 \u2013 Jun 14, 2026", 47, 72.0, 847, 'XAUUSD', 312, 90,
            'https://t.me/omnibrainsignals_vip')
        print(f"  Telegram:\n{tg}")
        r2 = gen.generate_story_card(1, 72.0, 8.47, 'XAUUSD', 312)
        print(f"  Story: {r2.get('image', 'N/A')}")
        print("=" * 60)

    elif '--run' in sys.argv:
        idx = sys.argv.index('--run')
        week = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else None
        result = get_generator().run_weekly_generation(week)
        print(json.dumps({k: v for k, v in result.items()
            if k != 'captions'}, indent=2, default=str))

    elif '--captions' in sys.argv:
        idx = sys.argv.index('--captions')
        week = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 1
        caps = get_generator().generate_captions(week, 47, 72.0, 8.47, 'XAUUSD', 312)
        for lang in ['en', 'hi', 'te', 'ar', 'es', 'fr', 'pt', 'ru', 'de', 'zh', 'ja', 'ko']:
            print(f"\n--- {lang.upper()} ---")
            print(caps[lang][:80] + ("..." if len(caps[lang]) > 80 else ""))

    elif '--story' in sys.argv:
        r = get_generator().generate_story_card(1, 72.0, 8.47, 'XAUUSD', 312)
        print(f"Story: {r}")

    elif '--state' in sys.argv:
        print(json.dumps(get_generator().state, indent=2))

    else:
        print("Usage: python proof_post_generator.py --test | --run [WEEK] |")
        print("       --captions [N] | --story | --state")
