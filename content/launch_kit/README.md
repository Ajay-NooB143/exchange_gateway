# OMNI BRAIN V2 — Week 1 Launch Kit

## Files
- `broadcast_templates.txt` — Telegram announcement templates
- `instagram_schedule.txt` — 7-day Instagram content calendar
- `vip_welcome_flow.txt` — Auto-welcome sequence on /verify
- `first_signal_announcement.txt` — First signal hype template

## Bot Hooks (telegram_signals.py)
On `/verify {chat_id}` success, call:
```python
from subscription_manager import get_subscription_manager
mgr = get_subscription_manager()
msg = mgr.format_welcome_message(chat_id, 30)
# send msg to chat_id via Telegram bot
```
