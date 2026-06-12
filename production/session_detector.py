"""
Smart Session Overlap Detector - OMNI BRAIN V2
Detects exact session states and assigns score weights.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from pathlib import Path

log = logging.getLogger('SessionDetector')

class SessionDetector:
    SESSIONS = {
        'Sydney': (22, 7),
        'Tokyo': (0, 9),
        'London': (8, 17),
        'New York': (13, 22),
    }
    
    OVERLAP_SCORES = {
        'Tokyo/London': (8, 9, 5),
        'London/NY': (13, 17, 15),
    }
    
    DEAD_ZONE = (20, 23)
    
    BEST_PAIRS = {
        'XAUUSD': ['London', 'New York'],
        'EURUSD': ['London', 'New York'],
        'GBPUSD': ['London'],
        'SP500': ['New York'],
        'US30': ['New York'],
        'NAS100': ['New York'],
        'USDJPY': ['Tokyo', 'London'],
        'USDCHF': ['London', 'New York'],
        'AUDUSD': ['Sydney', 'Tokyo'],
        'USDCAD': ['New York'],
        'USOIL': ['New York'],
    }
    
    def get_session_info(self, hour_utc: Optional[int] = None, symbol: Optional[str] = None) -> Dict:
        if hour_utc is None:
            hour_utc = datetime.now(timezone.utc).hour
        
        active = []
        for name, (start, end) in self.SESSIONS.items():
            if start <= hour_utc < end:
                active.append(name)
            elif start > end and (hour_utc >= start or hour_utc < end):
                active.append(name)
        
        dead_zone = self.DEAD_ZONE[0] <= hour_utc < self.DEAD_ZONE[1]
        
        overlap = None
        overlap_score = 0
        for name, (start, end, score) in self.OVERLAP_SCORES.items():
            if start <= hour_utc < end:
                overlap = name
                overlap_score = score
                break
        
        session_score = self._calculate_session_score(hour_utc)
        
        best_pairs = []
        avoid_pairs = []
        for sess in active:
            for pair, best_sessions in self.BEST_PAIRS.items():
                if sess in best_sessions:
                    if pair not in best_pairs:
                        best_pairs.append(pair)
        
        if dead_zone:
            avoid_pairs = list(self.BEST_PAIRS.keys())
        
        mins_to_london = None
        mins_to_ny = None
        if hour_utc < 8:
            mins_to_london = (8 - hour_utc) * 60
        if hour_utc < 13:
            mins_to_ny = (13 - hour_utc) * 60
        
        return {
            'active_sessions': active,
            'overlap': overlap,
            'overlap_score': overlap_score,
            'session_score': session_score,
            'dead_zone': dead_zone,
            'best_pairs': best_pairs,
            'avoid_pairs': avoid_pairs,
            'minutes_to_london_open': mins_to_london,
            'minutes_to_ny_open': mins_to_ny,
            'hour_utc': hour_utc,
        }
    
    def _calculate_session_score(self, hour_utc: int) -> int:
        if 8 <= hour_utc < 10:
            return 15  # London open
        elif 13 <= hour_utc < 15:
            return 15  # NY open
        elif 13 <= hour_utc < 17:
            return 15  # London/NY overlap
        elif 0 <= hour_utc < 8:
            return 5   # Asian session
        elif 20 <= hour_utc < 23:
            return 0   # Dead zone
        else:
            return 8   # Outside killzone
    
    def format_terminal(self, symbol: Optional[str] = None) -> str:
        info = self.get_session_info(symbol=symbol)
        parts = [f"[SESS] Active: {', '.join(info['active_sessions']) or 'NONE'}"]
        if info['overlap']:
            parts.append(f"[SESS] Overlap: {info['overlap']} +{info['overlap_score']}pts")
        if info['dead_zone']:
            parts.append("[SESS] ⚠️ DEAD ZONE - signals blocked")
        return "\n".join(parts)

# Global instance
_detector: Optional[SessionDetector] = None
def get_session_detector() -> SessionDetector:
    global _detector
    if _detector is None:
        _detector = SessionDetector()
    return _detector
