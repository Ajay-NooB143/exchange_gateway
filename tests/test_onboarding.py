"""Tests for subscription_manager.py onboarding features - OMNI BRAIN V2"""
import sys
import os
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'production'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest


class TestAutoWelcome:
    def test_handle_start_english(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        result = sm.handle_start('test_eng', 'John', 'en')
        assert 'Welcome' in result or 'OMNI' in result
        assert 'FREE' in result or 'signal' in result.lower()

    def test_handle_start_hindi(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        result = sm.handle_start('test_hin', 'Raj', 'hi')
        assert result is not None
        assert len(result) > 20

    def test_handle_start_telugu(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        result = sm.handle_start('test_tel', 'Sai', 'te')
        assert result is not None
        assert len(result) > 20

    def test_handle_start_arabic(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        result = sm.handle_start('test_arb', 'Ahmed', 'ar')
        assert result is not None

    def test_handle_start_fallback_unknown_lang(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        result = sm.handle_start('test_unk', 'Bob', 'xx')
        assert result is not None

    def test_handle_start_stores_user(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        sm.handle_start('test_store', 'Alice', 'es')
        sub = sm.get_subscriber('test_store')
        assert sub is not None
        assert sub['tier'] == 'FREE'

    def test_supported_languages(self):
        from subscription_manager import SubscriptionManager
        langs = SubscriptionManager.supported_languages()
        assert isinstance(langs, dict)
        assert 'en' in langs
        assert 'hi' in langs
        assert 'te' in langs
        assert 'ar' in langs

    def test_welcome_message_english(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        msg = sm.get_welcome_message('en')
        assert 'Welcome' in msg or 'OMNI' in msg

    def test_welcome_message_hindi(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        msg = sm.get_welcome_message('hi')
        assert msg is not None
        assert len(msg) > 20

    def test_welcome_message_fallback(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        msg = sm.get_welcome_message('tl')
        assert msg is not None
        assert len(msg) > 20


class TestOnboarding:
    def test_onboarding_initial_progress(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        sm.handle_start('test_ob1', 'Test', 'en')
        progress = sm.get_onboarding_progress('test_ob1')
        assert progress is not None
        assert 'day' in progress
        assert progress['day'] >= 0

    def test_advance_onboarding(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        sm.handle_start('test_ob2', 'Test', 'en')
        result = sm.advance_onboarding('test_ob2')
        assert result is not None

    def test_get_onboarding_messages_all_days(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        for day in range(1, 8):
            msg = sm.get_onboarding_message(day, 'en')
            assert msg is not None, f"Day {day} message is None"
            assert len(msg) > 10, f"Day {day} message too short"

    def test_onboarding_day_1_content(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        msg = sm.get_onboarding_message(1, 'en')
        assert 'signal' in msg.lower() or 'read' in msg.lower()

    def test_onboarding_day_2_confidence_scores(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        msg = sm.get_onboarding_message(2, 'en')
        assert 'EXECUTE' in msg or 'score' in msg.lower() or '75' in msg

    def test_onboarding_day_7_vip(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        msg = sm.get_onboarding_message(7, 'en')
        assert 'VIP' in msg or 'vip' in msg.lower()

    def test_user_timezone(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        offset = sm.get_user_timezone_offset('hi')
        assert offset == 5.5


class TestReEngagement:
    def test_inactive_users_check(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        inactive = sm.check_inactive_users(7)
        assert isinstance(inactive, list)

    def test_re_engagement_level_1(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        msg = sm.get_re_engagement_message(1)
        assert msg is not None
        assert len(msg) > 10

    def test_re_engagement_level_2(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        msg = sm.get_re_engagement_message(2)
        assert msg is not None


class TestReferrals:
    def test_referral_code_generation(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        code = sm.generate_referral_code('test_ref1')
        assert code is not None
        assert len(code) >= 6

    def test_get_referral_code(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        code = sm.get_referral_code('test_ref2')
        assert code is not None

    def test_referral_stats(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        stats = sm.get_referral_stats('test_ref3')
        assert isinstance(stats, dict)
        assert 'code' in stats or 'referred_users' in stats


class TestGrowthAnalytics:
    def test_track_interaction(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        sm.handle_start('test_ga1', 'Test', 'en')
        sm.track_interaction('test_ga1')
        sub = sm.get_subscriber('test_ga1')
        assert sub is not None

    def test_growth_analytics_structure(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        analytics = sm.get_growth_analytics()
        assert 'total_users' in analytics
        assert 'new_today' in analytics
        assert 'language_distribution' in analytics

    def test_daily_growth(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        daily = sm.get_daily_growth()
        assert isinstance(daily, int)

    def test_format_growth_report(self):
        from subscription_manager import SubscriptionManager
        sm = SubscriptionManager()
        report = sm.format_growth_report()
        assert report is not None
        assert len(report) > 10
