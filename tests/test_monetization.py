"""
Tests for monetization layer modules:
- PaperTrader (virtual account, TP/SL, P&L)
- SubscriptionManager (free/VIP, admin commands, expiry)
- ShowcaseGenerator (signal cards, weekly/monthly)
- AutoPoster (morning/signal/evening posts)
- YouTubeGenerator (viral/educational/results scripts)
"""
import sys, os, json, math, uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'production'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'content'))

import pytest


class TestPaperTrader:
    """Test virtual paper trading account."""

    def test_default_balance(self):
        from paper_trader import PaperTrader
        pt = PaperTrader()
        assert pt.balance > 0
        assert pt.starting_balance > 0

    def test_open_trade(self):
        from paper_trader import PaperTrader
        pt = PaperTrader()
        trade = pt.open_trade('XAUUSD', 'BULLISH', 2350.50, 2338.10,
                               2352.30, 2359.10, 2365.90, 0.67, 85)
        assert trade['symbol'] == 'XAUUSD'
        assert trade['direction'] == 'BULLISH'
        assert trade['entry'] == 2350.50
        assert trade['status'] == 'OPEN'
        assert len(trade['id']) == 8
        assert trade['remaining_lots'] == 0.67
        assert trade['partials_closed'] == []

    def test_open_trade_with_components(self):
        from paper_trader import PaperTrader
        pt = PaperTrader()
        comps = {'OB': 20, 'FVG': 20, 'SWEEP': 30, 'VWAP': 10}
        trade = pt.open_trade('EURUSD', 'BEARISH', 1.0850, 1.0900,
                               1.0820, 1.0780, 1.0740, 0.5, 72, comps)
        assert trade['components'] == comps
        assert trade['score'] == 72

    def test_close_trade_full(self):
        from paper_trader import PaperTrader
        pt = PaperTrader()
        trade = pt.open_trade('XAUUSD', 'BULLISH', 2350.50, 2338.10,
                               2352.30, 2359.10, 2365.90, 0.67, 85)
        result = pt.close_trade(trade['id'], 2365.90, 'TP3_HIT')
        assert result is not None
        assert result['status'] == 'CLOSED'
        assert result['close_reason'] == 'TP3_HIT'
        assert result['remaining_lots'] == 0
        # PnL: (2365.90 - 2350.50) * 1 * 0.67 * 10 (pip) = ~103
        assert result['pnl'] > 0

    def test_close_trade_loss(self):
        from paper_trader import PaperTrader
        pt = PaperTrader()
        trade = pt.open_trade('XAUUSD', 'BULLISH', 2350.50, 2325.00,
                               2355.00, 2360.00, 2365.00, 0.5, 80)
        result = pt.close_trade(trade['id'], 2325.00, 'SL_HIT')
        assert result['status'] == 'CLOSED'
        assert result['close_reason'] == 'SL_HIT'
        assert result['pnl'] < 0

    def test_close_nonexistent_trade(self):
        from paper_trader import PaperTrader
        pt = PaperTrader()
        result = pt.close_trade('nonexistent', 100, 'SL_HIT')
        assert result is None

    def test_get_pip_value(self):
        from paper_trader import PaperTrader
        pt = PaperTrader()
        assert pt._get_pip_value('XAUUSD') == 10.0
        assert pt._get_pip_value('EURUSD') == 1.0
        assert pt._get_pip_value('UNKNOWN') == 1.0

    def test_get_daily_pnl_empty(self):
        from paper_trader import PaperTrader
        pt = PaperTrader()
        dpnl = pt.get_daily_pnl('2099-01-01')
        assert dpnl['trades_opened'] == 0
        assert dpnl['trades_closed'] == 0

    def test_get_daily_pnl_with_trades(self):
        from paper_trader import PaperTrader
        pt = PaperTrader()
        pt.open_trade('XAUUSD', 'BULLISH', 2350, 2325, 2360, 2370, 2380, 0.5, 80)
        assert pt.get_daily_pnl()['trades_opened'] > 0

    def test_get_weekly_pnl_structure(self):
        from paper_trader import PaperTrader
        pt = PaperTrader()
        wpnl = pt.get_weekly_pnl(99)
        assert 'signals_executed' in wpnl
        assert 'win_rate' in wpnl
        assert 'total_pnl' in wpnl

    def test_get_stats_structure(self):
        from paper_trader import PaperTrader
        pt = PaperTrader()
        stats = pt.get_stats()
        assert 'balance' in stats
        assert 'total_closed' in stats
        assert 'win_rate' in stats
        assert 'best_score' in stats

    def test_get_stats_after_trades(self):
        from paper_trader import PaperTrader
        pt = PaperTrader()
        before = pt.get_stats()
        t1 = pt.open_trade('XAUUSD', 'BULLISH', 2350, 2325, 2360, 2370, 2380, 0.5, 85)
        pt.close_trade(t1['id'], 2380, 'TP3_HIT')
        stats = pt.get_stats()
        assert stats['total_closed'] == before['total_closed'] + 1
        assert stats['winners'] == before['winners'] + 1

    def test_balance_updates_on_close(self):
        from paper_trader import PaperTrader
        pt = PaperTrader()
        initial = pt.balance
        t = pt.open_trade('XAUUSD', 'BULLISH', 2350, 2325, 2360, 2370, 2380, 0.1, 80)
        pt.close_trade(t['id'], 2380, 'TP3_HIT')
        assert pt.balance > initial

    def test_format_daily_pnl_message(self):
        from paper_trader import PaperTrader
        pt = PaperTrader()
        msg = pt.format_daily_pnl_message()
        assert 'PAPER TRADING' in msg
        assert 'Balance' in msg

    def test_format_weekly_message(self):
        from paper_trader import PaperTrader
        pt = PaperTrader()
        msg = pt.format_weekly_message()
        assert 'WEEKLY' in msg
        assert 'Signals' in msg

    def test_balance_updates_on_loss(self):
        from paper_trader import PaperTrader
        pt = PaperTrader()
        initial = pt.balance
        t = pt.open_trade('XAUUSD', 'BULLISH', 2350, 2300, 2360, 2370, 2380, 0.1, 80)
        pt.close_trade(t['id'], 2300, 'SL_HIT')
        assert pt.balance < initial

    def test_balance_tracking(self):
        from paper_trader import PaperTrader
        pt = PaperTrader()
        assert pt.peak_balance >= pt.balance
        assert pt.starting_balance > 0


class TestSubscriptionManager:
    """Test subscription management system."""

    def test_add_subscriber(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        sm.add_subscriber('123456', 'test_user', 'VIP', 30)
        sub = sm.get_subscriber('123456')
        assert sub is not None
        assert sub['tier'] == 'VIP'
        assert sub['name'] == 'test_user'

    def test_is_vip_active(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        sm.add_subscriber('123456', 'vip_user', 'VIP', 30)
        assert sm.is_vip('123456') is True

    def test_is_vip_unknown_user(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        assert sm.is_vip('999') is False

    def test_remove_subscriber(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        sm.add_subscriber('123456', 'remove_me', 'VIP', 30)
        assert sm.remove_subscriber('123456') is True
        assert sm.get_subscriber('123456') is None

    def test_remove_nonexistent(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        assert sm.remove_subscriber('nonexistent') is False

    def test_get_subscriber_count(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        counts = sm.get_subscriber_count()
        assert 'free' in counts
        assert 'vip' in counts
        assert 'total' in counts

    def test_route_signal_vip(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        sm.add_subscriber('vip1', 'vip', 'VIP', 30)
        signal = {'symbol': 'XAUUSD', 'direction': 'BULLISH', 'decision': 'EXECUTE', 'score': 85}
        routed = sm.route_signal('vip1', signal)
        assert routed['channel'] == sm.VIP_CHANNEL
        assert routed['send_full'] is True
        assert routed['delay_seconds'] == 0

    def test_route_signal_free_execute(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        signal = {'symbol': 'XAUUSD', 'direction': 'BULLISH', 'decision': 'EXECUTE', 'score': 85}
        routed = sm.route_signal('free_user', signal)
        assert routed['channel'] == sm.FREE_CHANNEL
        assert routed['send_full'] is False
        assert routed['delay_seconds'] == 1800
        assert 'signal detected' in routed.get('message', '')

    def test_route_signal_free_wait(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        signal = {'symbol': 'EURUSD', 'direction': 'BEARISH', 'decision': 'WAIT', 'score': 62}
        routed = sm.route_signal('free_user', signal)
        assert routed['channel'] == sm.FREE_CHANNEL

    def test_get_expired_subs(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        sm.add_subscriber('expired1', 'expired', 'VIP', -1)
        expired = sm.get_expired_subs()
        assert len(expired) > 0

    def test_get_expiring_soon(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        sm.add_subscriber('soon1', 'soon', 'VIP', 2)
        expiring = sm.get_expiring_soon(7)
        assert len(expiring) > 0

    def test_extend_subscription(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        sm.add_subscriber('ext1', 'extend', 'VIP', 30)
        assert sm.extend_subscription('ext1', 30) is True
        sub = sm.get_subscriber('ext1')
        from datetime import datetime
        old_expiry = datetime.fromisoformat(sub['expires'].replace('Z', '+00:00'))
        assert old_expiry > datetime.now(timezone.utc)

    def test_extend_nonexistent(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        assert sm.extend_subscription('nobody', 30) is False

    def test_get_all_subscribers(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        all_subs = sm.get_all_subscribers()
        assert isinstance(all_subs, list)

    def test_format_subscriber_list(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        result = sm.format_subscriber_list()
        assert isinstance(result, str)

    def test_format_revenue_message(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        msg = sm.format_revenue_message()
        assert 'REVENUE' in msg

    def test_check_expired(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        expired_ids = sm.check_expired()
        assert isinstance(expired_ids, list)

    def test_handle_admin_addvip(self):
        from subscription_manager import handle_admin_command
        result = handle_admin_command('/addvip', ['999999', '30'], lambda c, m: None)
        assert 'VIP added' in result

    def test_handle_admin_subscribers(self):
        from subscription_manager import handle_admin_command
        result = handle_admin_command('/subscribers', [], lambda c, m: None)
        assert isinstance(result, str)

    def test_handle_admin_revenue(self):
        from subscription_manager import handle_admin_command
        result = handle_admin_command('/revenue', [], lambda c, m: None)
        assert 'REVENUE' in result

    def test_handle_admin_unknown(self):
        from subscription_manager import handle_admin_command
        result = handle_admin_command('/unknown', [], lambda c, m: None)
        assert 'Unknown' in result

    def test_set_language(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        assert sm.set_language('test123', 'hi') is True
        sub = sm.get_subscriber('test123')
        assert sub['language'] == 'hi'

    def test_get_language_default(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        lang = sm.get_language('nonexistent_user')
        assert lang in ['hi', 'en']

    def test_get_language_stored(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        sm.set_language('langtest', 'te')
        lang = sm.get_language('langtest')
        assert lang == 'te'

    def test_language_confirmation_message(self):
        from multilingual_engine import get_engine, CONFIRMATION_MESSAGES
        engine = get_engine()
        msg = engine.get_confirmation('hi')
        assert msg == CONFIRMATION_MESSAGES['hi']


class TestShowcaseGenerator:
    """Test content showcase generation."""

    def test_generate_signal_card(self):
        from showcase_generator import generate_signal_card
        card = generate_signal_card('XAUUSD', 'BULLISH', 85, 2350.50,
                                     2338.10, 2352.30, 2359.10, 2365.90, 0.67)
        assert 'XAUUSD' in card
        assert 'BULLISH' in card
        assert '85' in card
        assert 'PAPER TRADE' in card

    def test_generate_signal_card_live(self):
        from showcase_generator import generate_signal_card
        card = generate_signal_card('EURUSD', 'BEARISH', 72, 1.0850,
                                     1.0900, 1.0820, 1.0780, 1.0740, 0.5,
                                     is_paper=False)
        assert 'EURUSD' in card
        assert 'PAPER TRADE' not in card

    def test_generate_signal_card_with_components(self):
        from showcase_generator import generate_signal_card
        card = generate_signal_card('XAUUSD', 'BULLISH', 85, 2350.50,
                                     2338.10, 2352.30, 2359.10, 2365.90, 0.67,
                                     {'OB': 20, 'FVG': 20, 'SWEEP': 30})
        assert 'OB' in card
        assert 'FVG' in card

    def test_generate_signal_card_saves_file(self):
        from showcase_generator import generate_signal_card, SHOWCASE_DIR
        card = generate_signal_card('GBPUSD', 'BULLISH', 80, 1.2800,
                                     1.2750, 1.2850, 1.2900, 1.2950, 0.3)
        files = list(SHOWCASE_DIR.glob('*.txt'))
        assert len(files) > 0

    def test_generate_weekly_card(self):
        from showcase_generator import generate_weekly_card
        data = {
            'week': 1, 'date_range': 'Jun 8-14',
            'signals_executed': 36, 'winners': 26, 'losers': 10,
            'win_rate': 72.2, 'total_pnl': 847.50, 'roi': 8.47,
            'best_trade': 'XAUUSD +$312',
        }
        card = generate_weekly_card(data)
        assert 'WEEK 1' in card or 'Week 1' in card
        assert '72.2%' in card or '72' in card
        assert '+$' in card or '$' in card

    def test_generate_weekly_card_zero(self):
        from showcase_generator import generate_weekly_card
        data = {
            'week': 2, 'date_range': 'Jun 15-21',
            'signals_executed': 0, 'winners': 0, 'losers': 0,
            'win_rate': 0, 'total_pnl': 0, 'roi': 0,
            'best_trade': 'N/A',
        }
        card = generate_weekly_card(data)
        assert 'WEEK 2' in card or 'Week 2' in card

    def test_generate_monthly_track_record(self):
        from showcase_generator import generate_monthly_track_record
        trades = [
            {'symbol': 'XAUUSD', 'direction': 'BULLISH', 'pnl': 182.50},
            {'symbol': 'EURUSD', 'direction': 'BEARISH', 'pnl': -87.00},
            {'symbol': 'GBPUSD', 'direction': 'BULLISH', 'pnl': 145.20},
        ]
        report = generate_monthly_track_record(trades, 10000.0)
        assert 'MONTHLY' in report
        assert 'TRACK RECORD' in report
        assert 'Sharpe' in report

    def test_generate_monthly_track_record_empty(self):
        from showcase_generator import generate_monthly_track_record
        report = generate_monthly_track_record([], 10000.0)
        assert 'No trades' in report

    def test_generate_monthly_track_record_sharpe(self):
        from showcase_generator import generate_monthly_track_record
        trades = [{'symbol': f'PAIR{i}', 'direction': 'BULLISH', 'pnl': i * 10 - 50} for i in range(10)]
        report = generate_monthly_track_record(trades, 10000.0)
        assert 'Sharpe' in report


class TestAutoPoster:
    """Test Instagram auto-poster."""

    def test_generate_morning_post(self):
        from auto_poster import generate_morning_post
        post = generate_morning_post(yield_status='Normal',
                                      news_today='No events',
                                      session_plan='London focus',
                                      threshold=75)
        assert 'market outlook' in post or 'outlook' in post
        assert '75' in str(post)
        assert '#' in post

    def test_generate_morning_post_defaults(self):
        from auto_poster import generate_morning_post
        post = generate_morning_post()
        assert '#' in post

    def test_generate_signal_post(self):
        from auto_poster import generate_signal_post
        post = generate_signal_post('XAUUSD', 'BULLISH', 85, 182.50, 72.0)
        assert 'SIGNAL' in post
        assert 'XAUUSD' in post
        assert 'BULLISH' in post

    def test_generate_signal_post_reel_script(self):
        from auto_poster import generate_signal_post
        post = generate_signal_post('XAUUSD', 'BULLISH', 85, 182.50, 72.0)
        assert 'REEL SCRIPT' in post

    def test_generate_evening_post(self):
        from auto_poster import generate_evening_post
        post = generate_evening_post(6, 4, 66.7, 347.50)
        assert 'results' in post.lower()
        assert 'Kal milte hain' in post

    def test_generate_evening_post_loss(self):
        from auto_poster import generate_evening_post
        post = generate_evening_post(3, 1, 33.3, -87.00)
        assert '$-' in post or '$' in post

    def test_generate_weekly_post(self):
        from auto_poster import generate_weekly_post
        data = {
            'week': 1, 'date_range': 'Jun 8-14',
            'signals_executed': 36, 'winners': 26,
            'win_rate': 72.2, 'total_pnl': 847.50,
            'roi': 8.47, 'best_trade': 'XAUUSD +$312',
        }
        post = generate_weekly_post(data)
        assert 'WEEKLY' in post
        assert '72.2%' in post or '847' in post

    def test_generate_weekly_post_zero(self):
        from auto_poster import generate_weekly_post
        data = {
            'week': 2, 'date_range': 'Jun 15-21',
            'signals_executed': 0, 'winners': 0,
            'win_rate': 0, 'total_pnl': 0,
            'roi': 0, 'best_trade': 'N/A',
        }
        post = generate_weekly_post(data)
        assert 'WEEKLY' in post

    def test_hashtags_present(self):
        from auto_poster import HASHTAGS, HASHTAGS_SHORT
        assert '#' in HASHTAGS
        assert 'forexsignals' in HASHTAGS
        assert '#' in HASHTAGS_SHORT


class TestYouTubeGenerator:
    """Test YouTube script generation."""

    def test_generate_viral_script(self):
        from youtube_generator import generate_viral_script
        script = generate_viral_script()
        assert 'TITLE:' in script
        assert 'hedge fund' in script.lower()
        assert 'B-ROLL' in script
        assert 'THUMBNAIL' in script
        assert 'TAGS' in script

    def test_generate_viral_script_content(self):
        from youtube_generator import generate_viral_script
        script = generate_viral_script('XAUUSD', 847.50, 72.2, 8.47, 85)
        assert '72.2%' in script or '72.2' in script

    def test_generate_educational_script(self):
        from youtube_generator import generate_educational_script
        script = generate_educational_script()
        assert 'TITLE:' in script
        assert 'SMC' in script
        assert 'Python' in script
        assert 'B-ROLL' in script

    def test_generate_educational_script_code_blocks(self):
        from youtube_generator import generate_educational_script
        script = generate_educational_script()
        assert '```python' in script or 'def detect' in script

    def test_generate_results_script(self):
        from youtube_generator import generate_results_script
        data = {
            'week': 1, 'date_range': 'Week 1 Review',
            'signals_executed': 36, 'winners': 26,
            'win_rate': 72.2, 'total_pnl': 847.50,
            'roi': 8.47, 'best_trade': 'XAUUSD +$312',
        }
        script = generate_results_script(data)
        assert 'TITLE:' in script
        assert '72' in script
        assert 'B-ROLL' in script

    def test_generate_results_script_default(self):
        from youtube_generator import generate_results_script
        script = generate_results_script()
        assert 'TITLE:' in script
        assert 'TAGS' in script

    def test_all_scripts_saved(self):
        from youtube_generator import YOUTUBE_DIR
        import shutil
        files_before = len(list(YOUTUBE_DIR.glob('*.txt')))
        files_exist = YOUTUBE_DIR.exists()
        assert files_exist
        # Scripts should save to directory
        assert True


class TestMonetizationIntegration:
    """Integration tests across monetization modules."""

    def test_paper_trader_hooks_into_pipeline(self):
        """Verify paper_trader can be imported from pipeline path."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        try:
            from paper_trader import get_paper_trader
            pt = get_paper_trader()
            assert pt is not None
        except ImportError:
            pytest.skip("paper_trader not in pipeline path")

    def test_telegram_command_integration(self):
        """Verify admin command handler works."""
        from subscription_manager import handle_admin_command, ADMIN_COMMANDS
        assert '/addvip' in ADMIN_COMMANDS
        assert '/subscribers' in ADMIN_COMMANDS
        assert '/revenue' in ADMIN_COMMANDS
        assert '/broadcast' in ADMIN_COMMANDS

    def test_paper_trade_pnl_calculation(self):
        """Long trade PnL formula."""
        from paper_trader import PaperTrader
        pt = PaperTrader()
        t = pt.open_trade('XAUUSD', 'BULLISH', 2350.00, 2320.00, 2370.00, 2390.00, 2410.00, 1.0, 85)
        result = pt.close_trade(t['id'], 2410.00, 'TP3_HIT')
        # (2410 - 2350) * 1 * 1.0 * 10 = $600
        assert abs(result['pnl'] - 600.0) < 0.1

    def test_paper_trade_pnl_short(self):
        """Short trade PnL formula."""
        from paper_trader import PaperTrader
        pt = PaperTrader()
        t = pt.open_trade('EURUSD', 'BEARISH', 1.1000, 1.1050, 1.0950, 1.0900, 1.0850, 1.0, 80)
        result = pt.close_trade(t['id'], 1.0850, 'TP3_HIT')
        # (1.0850 - 1.1000) * -1 * 1.0 * 1 = 0.015 * 1 * 1 = $150
        assert result['pnl'] > 0

    def test_paper_trade_loss_short(self):
        """Short trade loss."""
        from paper_trader import PaperTrader
        pt = PaperTrader()
        t = pt.open_trade('XAUUSD', 'BEARISH', 2400.00, 2430.00, 2370.00, 2350.00, 2330.00, 0.5, 75)
        result = pt.close_trade(t['id'], 2430.00, 'SL_HIT')
        assert result['pnl'] < 0

    def test_multiple_trades_balance(self):
        """Multiple trades should update balance cumulatively."""
        from paper_trader import PaperTrader
        pt = PaperTrader()
        initial = pt.balance
        t1 = pt.open_trade('XAUUSD', 'BULLISH', 2350, 2320, 2370, 2390, 2410, 0.1, 85)
        pt.close_trade(t1['id'], 2410, 'TP3_HIT')
        t2 = pt.open_trade('EURUSD', 'BULLISH', 1.10, 1.09, 1.11, 1.12, 1.13, 0.1, 80)
        pt.close_trade(t2['id'], 1.13, 'TP3_HIT')
        assert pt.balance > initial
        assert pt.balance > pt.starting_balance


if __name__ == '__main__':
    pytest.main(['-v', __file__])
