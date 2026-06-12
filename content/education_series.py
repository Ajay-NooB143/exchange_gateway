"""
30-Day Educational Trading Series Generator — OMNI BRAIN V2
=============================================================
Generates Instagram, Telegram, and YouTube Shorts content
for all 32 languages using the Multilingual Engine.

Usage:
  python education_series.py --day 1        # Generate day 1 only
  python education_series.py --all          # Generate all 30 days
  python education_series.py --test         # Test with 4 languages
"""

import logging
import sys
from pathlib import Path

from content.multilingual_engine import get_engine, LANGUAGES

log = logging.getLogger('EducationSeries')

DAYS = [
    (1, "what_is_forex", "What is Forex?"),
    (2, "what_is_pip", "What is a Pip?"),
    (3, "what_is_leverage", "What is Leverage?"),
    (4, "what_is_spread", "What is a Spread?"),
    (5, "market_sessions", "Market Sessions"),
    (6, "what_is_smart_money", "What is Smart Money?"),
    (7, "order_blocks", "Order Blocks Explained"),
    (8, "fair_value_gaps", "Fair Value Gaps (FVG)"),
    (9, "liquidity_sweeps", "Liquidity Sweeps"),
    (10, "break_of_structure", "Break of Structure (BOS)"),
    (11, "multi_timeframe", "Multi-Timeframe Analysis"),
    (12, "vwap_explained", "VWAP Explained"),
    (13, "support_resistance", "Support & Resistance"),
    (14, "trend_identification", "Trend Identification"),
    (15, "entry_exit_rules", "Entry & Exit Rules"),
    (16, "position_sizing", "Position Sizing"),
    (17, "stop_loss_placement", "Stop Loss Placement"),
    (18, "take_profit_strategy", "Take Profit Strategy"),
    (19, "risk_reward_ratio", "Risk:Reward Ratio"),
    (20, "kelly_criterion", "Kelly Criterion"),
    (21, "trading_psychology", "Trading Psychology"),
    (22, "fomo_explained", "FOMO Explained"),
    (23, "revenge_trading", "Revenge Trading"),
    (24, "patience_in_trading", "Patience in Trading"),
    (25, "building_discipline", "Building Discipline"),
    (26, "correlation_trading", "Correlation Trading"),
    (27, "news_trading", "News Trading"),
    (28, "yield_curve_impact", "Yield Curve Impact"),
    (29, "sentiment_analysis", "Sentiment Analysis"),
    (30, "building_your_system", "Building Your System"),
]


def _instagram_en(day_num, topic, title):
    topics = {
        "what_is_forex": (
            "Forex, short for foreign exchange, is the world's largest financial market where currencies are traded 24 hours a day, five days a week. With a daily trading volume exceeding $7.5 trillion, it dwarfs every other financial market on the planet.",
            [
                "Currencies always trade in pairs — you buy one and sell the other simultaneously",
                "The market is decentralized with no central exchange, operating globally via banks and brokers",
                "Major pairs like EUR/USD offer the tightest spreads and highest liquidity",
            ],
            "Start by learning the major pairs first: EUR/USD, GBP/USD, USD/JPY, and USD/CHF. These have the lowest costs and most predictable behavior."
        ),
        "what_is_pip": (
            "A pip — which stands for 'percentage in point' — is the smallest price move a currency pair can make. For most major pairs, a pip is 0.0001. It is the fundamental unit you use to measure your profit or loss in every trade.",
            [
                "One pip on EUR/USD equals 0.0001, while on USD/JPY it equals 0.01",
                "Most brokers now offer fractional pips (pipettes) for tighter precision",
                "Your profit or loss is calculated by multiplying pips moved by your position size",
            ],
            "Open a demo account and measure how many pips each setup moves before you risk real money. Knowing the average pip range of your pairs is essential."
        ),
        "what_is_leverage": (
            "Leverage lets you control a large position with a small amount of capital. If your broker offers 1:100 leverage, a $1,000 deposit lets you control $100,000 worth of currency. This amplifies both gains and losses dramatically.",
            [
                "Higher leverage multiplies both profits AND losses — it is a double-edged sword",
                "A 1:100 leverage means a 1% market move results in a 100% gain or loss on your margin",
                "Smart traders use low leverage (1:10 to 1:30) and focus on position sizing instead",
            ],
            "Never use more than 1:10 leverage until you have been consistently profitable for six months. Treat leverage as a tool, not a lottery ticket."
        ),
        "what_is_spread": (
            "The spread is the difference between the bid (sell) price and the ask (buy) price of a currency pair. It is essentially the commission your broker charges you for executing the trade. Lower spreads mean lower costs.",
            [
                "Major pairs like EUR/USD have spreads as low as 0.1 pips with ECN brokers",
                "Exotic pairs like USD/TRY can have spreads of 50+ pips during volatile sessions",
                "Spreads widen during news events and outside peak market hours — trade when liquidity is high",
            ],
            "Always check the spread before entering a trade. If the spread eats more than 20% of your target profit, skip the trade. Costs compound over time."
        ),
        "market_sessions": (
            "The forex market operates 24 hours a day through four major trading sessions: Sydney, Tokyo, London, and New York. Each session has unique characteristics, volatility levels, and currency pairs that perform best.",
            [
                "London session sees the highest volume with 35% of all trades — EUR, GBP pairs thrive",
                "Tokyo session drives USD/JPY and yen crosses with distinct Asian range behavior",
                "The London-New York overlap (12:00-16:00 GMT) has the highest volatility and best trading opportunities",
            ],
            "Focus on trading only one session until you master its rhythm. The London-New York overlap is ideal for beginners due to liquidity and clear trends."
        ),
        "what_is_smart_money": (
            "Smart Money refers to the trading activity of institutional players — central banks, hedge funds, and large commercial banks. These entities move the market with massive order flow, and understanding their footprints can give you a significant edge.",
            [
                "Smart Money leaves traces on the chart through order blocks, imbalances, and liquidity sweeps",
                "Retail traders often trade against Smart Money — institutions target their stop losses",
                "Learning to identify institutional zones can improve your win rate by aligning you with the big players",
            ],
            "Stop trying to predict price direction. Instead, learn to identify where institutions have placed their orders. Price moves between liquidity pools."
        ),
        "order_blocks": (
            "An order block is a price zone where institutional traders have placed large pending orders. These zones act as strong support or resistance because big money is waiting there to enter or exit positions. They are the foundation of Smart Money Concepts.",
            [
                "Bullish order blocks form at the last bearish candle before a strong upward move",
                "Bearish order blocks form at the last bullish candle before a sharp downward move",
                "Order blocks work best on higher timeframes — 1-hour, 4-hour, and daily charts",
            ],
            "Draw order blocks on the daily chart first. Mark the last candle before a strong impulse move. Price will often return to these zones before continuing."
        ),
        "fair_value_gaps": (
            "A Fair Value Gap (FVG) occurs when buying or selling pressure is so intense that price gaps through an area without trading there. These imbalances act like magnets — price often returns to fill them before resuming the trend.",
            [
                "FVG forms between three consecutive candles when the wicks do not overlap",
                "Price returns to fill FVGs about 70% of the time before continuing the trend",
                "FVGs on higher timeframes (daily, weekly) are significantly more reliable",
            ],
            "Mark FVGs on the 4-hour chart. Wait for price to enter the gap zone and look for confirmation before entering. Do not trade every FVG — focus on the ones aligned with the trend."
        ),
        "liquidity_sweeps": (
            "A liquidity sweep occurs when price aggressively moves to take out a cluster of stop-loss orders or pending positions before reversing. These sweeps are institutional traps designed to trigger retail traders before the real move begins.",
            [
                "Sweeps happen at recent highs and lows where retail traders place their stops",
                "A liquidity sweep often comes with a sudden spike and quick reversal — a 'fakeout' pattern",
                "The best entries come right after a sweep when price shows rejection and starts moving back",
            ],
            "Draw key highs and lows on your chart. If price breaks a level but immediately reverses with strong momentum, the sweep likely just happened. Enter in the opposite direction."
        ),
        "break_of_structure": (
            "A Break of Structure (BOS) occurs when price breaks a key swing high or low, signaling that the current trend is likely to continue. BOS is the core confirmation signal in Smart Money Concepts and trend-following strategies.",
            [
                "In an uptrend, a BOS is when price breaks above a previous swing high",
                "In a downtrend, a BOS is when price breaks below a previous swing low",
                "A BOS combined with an order block or FVG creates a high-probability setup",
            ],
            "Never enter on a breakout alone. Wait for a BOS, then look for a retest of an order block or FVG in the same direction. This gives you a better risk-to-reward entry."
        ),
        "multi_timeframe": (
            "Multi-timeframe analysis means examining the same currency pair across different chart periods to get a complete picture. Higher timeframes show the macro trend, while lower timeframes reveal precise entry and exit points.",
            [
                "Use the daily chart to identify the overall trend and key support/resistance levels",
                "Use the 4-hour chart to find order blocks and FVGs aligned with the daily trend",
                "Use the 15-minute or 1-hour chart to fine-tune your entry with precision",
            ],
            "Start with the daily chart. Determine the trend. Drop to the 4-hour to find a setup. Drop to the 1-hour for entry. If all three timeframes agree, the trade has a higher probability of success."
        ),
        "vwap_explained": (
            "VWAP stands for Volume-Weighted Average Price. It shows the average price a currency has traded at throughout the day, weighted by volume. Institutional traders use VWAP to assess whether price is fair value or extended.",
            [
                "Price above VWAP suggests buying pressure — price is above the day's average",
                "Price below VWAP suggests selling pressure — price is below the day's average",
                "VWAP acts as dynamic support and resistance during intraday trading",
            ],
            "Use VWAP on the 15-minute chart. If price is above VWAP, look for long entries. If below, look for short entries. A strong move away from VWAP often reverts back to it."
        ),
        "support_resistance": (
            "Support and resistance are the most fundamental concepts in technical analysis. Support is a price level where buying pressure is strong enough to stop a decline. Resistance is where selling pressure stops an advance.",
            [
                "Support and resistance levels work best when they have been tested multiple times",
                "A level that was resistance often becomes support once broken, and vice versa",
                "Round numbers (like 1.2000 on EUR/USD) act as psychological support and resistance",
            ],
            "Draw the most obvious horizontal levels on the daily chart. The more times a level has been tested, the stronger it is. Wait for a touch near these levels before making a decision."
        ),
        "trend_identification": (
            "Trend identification is the skill of determining the market's current directional bias. Trends can be up, down, or sideways. The golden rule is to trade in the direction of the larger trend for higher success rates.",
            [
                "Higher highs and higher lows = uptrend. Lower highs and lower lows = downtrend",
                "The 200-period moving average on the 1-hour chart acts as a reliable trend filter",
                "Sideways (range-bound) markets require different strategies — buy at support, sell at resistance",
            ],
            "Use the 200 EMA on the 1-hour chart. If price is above it, only take long setups. If below, only take short setups. This single rule eliminates most losing trades."
        ),
        "entry_exit_rules": (
            "Entry and exit rules are the backbone of a profitable trading system. Without clear rules, you are gambling. Every trade needs a precise entry trigger, a stop loss, and at least one take profit target determined before you click buy or sell.",
            [
                "Your entry should be based on confluence — at least two reasons to take the trade",
                "Your stop loss must be placed at a level that invalidates your trade thesis",
                "Use multiple take-profit levels: 1:1, 1:2, and 1:3 risk-to-reward ratios",
            ],
            "Write down your entry and exit rules before every trading session. If the setup does not meet all your criteria, do not take the trade. Discipline beats prediction."
        ),
        "position_sizing": (
            "Position sizing determines how much of your capital you risk on a single trade. It is the single most important factor in long-term trading survival. Even a 50% win-rate strategy becomes profitable with proper position sizing.",
            [
                "Never risk more than 1-2% of your account on any single trade",
                "Use a position size calculator to determine lot size based on stop loss distance",
                "Smaller position sizes let you stay in the game longer — survival comes first",
            ],
            "Calculate your position size before every trade using this formula: Lot Size = (Account Balance × Risk %) / (Stop Loss in Pips × Pip Value). Aim for 1% risk per trade."
        ),
        "stop_loss_placement": (
            "A stop loss is your insurance policy against catastrophic losses. It is a pre-set order that closes your trade at a specific price to limit your downside. Without a stop loss, one bad trade can wipe out months of profits.",
            [
                "Place stops at levels that, if hit, prove your analysis was wrong",
                "Avoid placing stops at obvious round numbers where institutions hunt liquidity",
                "Use ATR (Average True Range) to set stop distances that account for market volatility",
            ],
            "Place your stop loss below the most recent swing low (for longs) or above the most recent swing high (for shorts). Add 5-10 pips buffer to avoid being stopped out by random noise."
        ),
        "take_profit_strategy": (
            "A take profit order locks in your gains when price reaches a predetermined target. Unlike stop losses, take profits are optional, but having a clear target prevents greed from turning winners into losers.",
            [
                "Use the previous swing high or low as your first take profit target",
                "Trail your stop loss to breakeven when price reaches your first target",
                "Let partial profits run by using a trailing stop on remaining position size",
            ],
            "Set two take-profit levels: TP1 at 1:1 risk-to-reward where you close 50% and move stop to breakeven. TP2 at 1:2 or 1:3 where you let the rest run with a trailing stop."
        ),
        "risk_reward_ratio": (
            "Risk-to-reward ratio (RRR) compares the potential profit of a trade to its potential loss. A 1:3 risk-to-reward ratio means you risk $100 to make $300. Consistently using favorable RRR is what separates profitable traders from everyone else.",
            [
                "Aim for a minimum 1:2 risk-to-reward ratio on every trade you take",
                "A 40% win rate with 1:3 RRR outperforms a 60% win rate with 1:1 RRR",
                "RRR is calculated before entry — if the target is not wide enough, skip the trade",
            ],
            "Before entering any trade, calculate: how many pips to stop vs how many pips to target. If the target is not at least double the risk, do not take that trade. Wait for better setups."
        ),
        "kelly_criterion": (
            "The Kelly Criterion is a mathematical formula that tells you exactly how much of your capital to risk on each trade based on your historical win rate and average risk-to-reward ratio. It maximizes long-term growth while minimizing drawdown.",
            [
                "Kelly % = Win Rate - (Loss Rate / Average RRR). A 50% win rate with 1:2 RRR gives Kelly = 50% - (50%/2) = 25%",
                "Most traders use fractional Kelly (25-50% of the full Kelly value) to reduce volatility",
                "If your Kelly is negative, your strategy has a negative expectancy and needs to be fixed",
            ],
            "Track your last 100 trades. Calculate your win rate and average RRR. Use the Kelly formula to find the optimal risk per trade, then use half of that value for safety."
        ),
        "trading_psychology": (
            "Trading psychology is the study of how emotions affect your trading decisions. Fear and greed are the two biggest enemies of every trader. Mastering your psychology is harder than mastering any strategy, and it separates professionals from amateurs.",
            [
                "Fear causes you to exit winners early and avoid high-probability setups",
                "Greed causes you to overtrade, increase position sizes, and hold losers too long",
                "Keeping a trading journal helps you identify and correct emotional patterns",
            ],
            "Journal every trade with a note on how you felt when entering and exiting. Review your journal weekly to spot emotional patterns. Awareness is the first step to mastery."
        ),
        "fomo_explained": (
            "FOMO — Fear Of Missing Out — is the emotional trigger that makes you chase a trade after price has already moved significantly. It is one of the most destructive forces in trading and the primary reason retail traders lose money.",
            [
                "FOMO entries happen when you see a big move and feel pressure to 'catch it'",
                "Chasing price almost always results in buying the top or selling the bottom",
                "The market always offers another opportunity — there is no such thing as 'the one that got away'",
            ],
            "When you feel FOMO, close the charts and walk away for 30 minutes. If the setup still looks good after that break, it might be worth taking. Most of the time, the urge will pass."
        ),
        "revenge_trading": (
            "Revenge trading is the act of immediately placing a new trade to recover a loss, often with a larger position size. It is an emotional spiral that turns a small loss into a blown account. The need to 'get even' is your ego fighting against the market.",
            [
                "Revenge trading increases position size, which means smaller moves can cause larger damage",
                "After a loss, your judgment is clouded — taking another trade immediately is a mistake",
                "The market does not care about your P&L — it is not personal, so do not make it personal",
            ],
            "After any losing trade, step away for at least one hour. If you lost more than 3% of your account in a day, stop trading entirely and come back tomorrow. Accept the loss and move on."
        ),
        "patience_in_trading": (
            "Patience is the ability to wait for high-probability setups that match your trading plan rather than forcing trades in low-quality conditions. The best traders in the world spend most of their time waiting and only act when the odds are stacked in their favor.",
            [
                "Waiting for the perfect setup often means watching 50-100 candles before a trade",
                "Being out of the market preserves your capital and your mental clarity",
                "Patience lets price come to your level instead of you chasing price",
            ],
            "Set a rule: you will not take more than three trades per day. This forces you to wait for only the best setups. Quality over quantity always wins in trading."
        ),
        "building_discipline": (
            "Discipline is the bridge between knowing what to do and actually doing it. Every trader knows they should use stop losses, follow their plan, and not overtrade. The disciplined trader actually does these things consistently, regardless of emotions.",
            [
                "Discipline is a habit built through repetition, not motivation — show up and follow the plan",
                "Create a pre-trade checklist and do not enter until every item is checked off",
                "Discipline means taking the same trade whether you are on a winning streak or a losing streak",
            ],
            "Create a physical checklist on paper. Before every trade, go through each item. If even one condition is not met, walk away. Do this for 30 days straight and discipline becomes automatic."
        ),
        "correlation_trading": (
            "Currency correlation measures how two currency pairs move in relation to each other. Positive correlation means pairs move in the same direction; negative correlation means they move in opposite directions. Understanding correlation prevents overexposure and uncovers hedging opportunities.",
            [
                "EUR/USD and GBP/USD typically have strong positive correlation (0.80+)",
                "EUR/USD and USD/CHF typically have strong negative correlation (-0.85+)",
                "Trading two highly correlated pairs doubles your risk, not your opportunity",
            ],
            "Before trading multiple pairs, check their correlation coefficient. Avoid taking the same direction trade on two positively correlated pairs — you are just doubling risk on essentially the same position."
        ),
        "news_trading": (
            "News trading involves taking positions around major economic releases like Non-Farm Payrolls, CPI, and central bank rate decisions. These events cause the highest volatility of the month, creating both enormous opportunity and significant risk.",
            [
                "News events can move prices 50-100 pips in seconds — tight stops will get run over",
                "The actual number vs the forecast determines the direction — anticipation already priced in",
                "Major news is released at scheduled times — always check an economic calendar before trading",
            ],
            "If you are new to news trading, do not enter during the first 15 minutes after a release. Let the initial volatility settle, then trade in the direction of the established post-news trend."
        ),
        "yield_curve_impact": (
            "The yield curve plots interest rates of government bonds across different maturities. Its shape — normal, inverted, or flat — provides essential clues about future economic conditions and directly impacts currency values through interest rate expectations.",
            [
                "An inverted yield curve (short-term rates higher than long-term) often predicts a recession",
                "A steepening yield curve suggests economic growth and typically strengthens the currency",
                "Central banks adjust rates based on yield curve signals, directly affecting forex pairs",
            ],
            "Check the 2-year vs 10-year Treasury yield spread weekly. If it is inverted, favor safe-haven currencies. If it is steepening, favor growth currencies. This macro view sets your trading bias."
        ),
        "sentiment_analysis": (
            "Sentiment analysis gauges the overall attitude of traders toward a currency or market. It answers the question: is everyone already bullish or bearish? Extreme sentiment is a powerful contrarian indicator — when everyone is crowded on one side, the reversal is near.",
            [
                "The COT (Commitment of Traders) report shows how institutional traders are positioned",
                "Retail trader sentiment data from brokers shows where the crowd is leaning",
                "When retail sentiment hits 80%+ in one direction, the market often reverses",
            ],
            "Use the FXStreet or Myfxbook sentiment tools weekly. If 80%+ of retail traders are long on a pair, look for signs of exhaustion and consider a short position. Be early, not late."
        ),
        "building_your_system": (
            "Building Your System is the final and most important lesson. A trading system is a complete set of rules that governs every aspect of your trading — from market selection to risk management to when to close a trade. A system removes emotion and makes your results repeatable.",
            [
                "Your system must include: entry rules, exit rules, position sizing, and a daily routine",
                "Backtest your system on at least 6 months of historical data before going live",
                "The best system is one you can follow consistently — simplicity beats complexity",
            ],
            "Start with a one-page document. Write your system rules in plain language. Trade it on demo for 100 trades. Tweak what does not work. Then and only then, go live with real money."
        ),
    }
    data = topics.get(topic, topics["what_is_forex"])
    description, points, tips = data
    points_text = "\n".join(f"• {p}" for p in points)
    return (
        f"📚 {title}\n\n"
        f"Welcome to Day {day_num} of our 30-day trading education series!\n\n"
        f"{description}\n\n"
        f"Key takeaways:\n"
        f"{points_text}\n\n"
        f"{tips}\n\n"
        f"Follow for more! 🚀"
    )


def _telegram_en(day_num, topic, title):
    topics = {
        "what_is_forex": (
            "Forex (foreign exchange) is the global marketplace for trading national currencies against each other. It is the largest and most liquid financial market in the world, with an average daily turnover of over $7.5 trillion. Unlike stock exchanges, forex operates 24 hours a day through a global network of banks, institutions, and brokers. Every trade involves simultaneously buying one currency while selling another, which is why currencies are always quoted in pairs — EUR/USD, GBP/JPY, USD/TRY, and so on. The market is driven by economic fundamentals, geopolitical events, interest rate differentials, and market sentiment. Retail traders access the market through brokers who provide leverage, allowing them to control large positions with relatively small capital.",
            [
                "The forex market never sleeps — it rotates through Sydney, Tokyo, London, and New York sessions",
                "Currencies are always traded in pairs — you buy one currency and sell the other",
                "Daily volume exceeds $7.5 trillion, making it impossible for any single entity to manipulate the market for long",
                "Major pairs (EUR/USD, GBP/USD, USD/JPY, USD/CHF) offer the best liquidity and lowest transaction costs",
                "Retail traders participate through forex brokers using margin accounts with leverage",
            ],
            "Open a free demo account with a regulated broker this week. Spend at least 15 minutes each day just watching how prices move on the EUR/USD pair. Do not trade yet — just observe how the market behaves at different times of day."
        ),
        "what_is_pip": (
            "A pip (percentage in point) is the smallest standardized price movement in a currency pair. For most pairs quoted to four decimal places, one pip equals 0.0001. For pairs involving the Japanese yen, one pip equals 0.01. Understanding pips is fundamental because all your profits, losses, and risk calculations are expressed in pips. When you hear a trader say 'I made 50 pips on that trade,' they mean the price moved 50 units of the fourth decimal place. Most brokers now offer fractional pip pricing (pipettes) which gives an extra decimal place for tighter spreads and more precise entries. The pip value in your account currency depends on both the pair you are trading and your position size.",
            [
                "For EUR/USD, GBP/USD, and most major pairs: 1 pip = 0.0001",
                "For USD/JPY and yen crosses: 1 pip = 0.01",
                "Pip value changes based on position size — a standard lot (100k units) equals $10 per pip on USD-quoted pairs",
                "Fractional pip pricing (e.g., 1.10543) allows for tighter spreads and more accurate entries",
                "Knowing the average pip range of your pairs helps you set realistic stop loss and take profit distances",
            ],
            "Calculate the pip value for each pair you plan to trade. If you trade a mini lot (10k units), a pip on EUR/USD is worth $1. Knowing your pip value lets you convert pips to real money before you enter any trade."
        ),
        "what_is_leverage": (
            "Leverage is a powerful tool that allows traders to control large positions with a fraction of the total value, known as margin. For example, with 1:100 leverage, a $1,000 deposit can control $100,000 in the market. This amplifies returns — a 1% move in your favor doubles your account. But the exact same math applies to losses. A 1% move against you wipes out your entire account. Professional traders treat leverage with immense respect. They rarely use more than 1:10 leverage, even when their brokers offer 1:500. The key is to understand that leverage magnifies the percentage move of your account relative to the percentage move of the market. Using less leverage and larger stop losses is mathematically superior to using high leverage with tight stops.",
            [
                "Leverage is expressed as a ratio: 1:50, 1:100, 1:500, meaning multiples of your capital",
                "Margin is the collateral required to open and maintain a leveraged position",
                "High leverage and tight stops is the fastest way to blow up an account",
                "Regulated brokers in the EU and UK cap retail leverage at 1:30 for major pairs",
                "Lower leverage with proper position sizing produces more consistent, sustainable growth",
            ],
            "Set your account leverage to no more than 1:30 if your broker allows adjustable leverage settings. Resolve that you will only use 1:10 or less for the first six months of live trading. Your future self will thank you."
        ),
        "what_is_spread": (
            "The spread is the transaction cost of opening a trade. It is the difference between the bid price (what you sell at) and the ask price (what you buy at). If EUR/USD has a bid of 1.1050 and an ask of 1.1052, the spread is 2 pips. That means you start every trade 2 pips in the red. The spread is how your broker makes money on commission-free accounts. Spreads vary dramatically based on market conditions. During the London-New York overlap, major pairs can have spreads as low as 0.1 pips with ECN brokers. During news events or Asian session on exotic pairs, spreads can widen to 50+ pips. Choosing the right broker and trading at the right times directly affects your profitability through spread costs.",
            [
                "Spread = Ask − Bid. You buy at the ask and sell at the bid, so you start each trade slightly negative",
                "ECN brokers offer raw spreads from 0.0 pips but charge a small commission per lot",
                "Spreads widen during news events, low liquidity periods, and on exotic currency pairs",
                "The London-New York session overlap (12:00-16:00 GMT) offers the tightest spreads",
                "Over a year, spread costs can eat 10-30% of your profits if you trade during bad hours",
            ],
            "Check your broker's spread on EUR/USD during the London session, Asian session, and during the next NFP news release. Note the difference. Then schedule your trading sessions around the tightest spreads."
        ),
        "market_sessions": (
            "The forex market operates through four major sessions that rotate around the globe as financial centers open and close. The Sydney session kicks off at 22:00 GMT, followed by Tokyo at 00:00 GMT, then London at 08:00 GMT, and finally New York at 13:00 GMT. Each session has distinct characteristics. The Asian session (Tokyo) is known for range-bound, low-volatility movements, with USD/JPY and yen crosses showing the most activity. The London session is the most volatile, handling about 35% of global forex volume — EUR and GBP pairs come alive here. The New York session brings high volatility as US economic data is released. The most powerful trading window is the London-New York overlap from 12:00 to 16:00 GMT, when volume and volatility peak simultaneously.",
            [
                "Asian session (Tokyo 00:00-09:00 GMT): low volatility, range-bound, best for JPY pairs",
                "London session (08:00-17:00 GMT): highest volume, strong trends, best for EUR and GBP pairs",
                "New York session (13:00-22:00 GMT): high volatility during US data releases, USD pairs active",
                "London-NY overlap (12:00-16:00 GMT): peak volume and volatility, best trading window of the day",
                "Weekends and major holidays see drastically lower volume — avoid trading then",
            ],
            "For one week, trade only during the London-NY overlap (12:00-16:00 GMT). Note how your setups perform compared to other times. Most traders find this window produces the cleanest trends and most reliable signals."
        ),
        "what_is_smart_money": (
            "Smart Money refers to the capital deployed by professional institutional traders — central banks, commercial banks, hedge funds, and pension funds. These entities control the vast majority of forex volume. Unlike retail traders who trade for quick profits, Smart Money operates with a long-term strategic view, accumulating positions gradually and using complex risk management. The core insight of Smart Money Concepts is that retail traders consistently lose because they are trading against these institutions. By learning to read the footprints left by institutional activity on price charts — order blocks, fair value gaps, liquidity sweeps, and breaks of structure — you can align your trades with the flow of Smart Money rather than against it.",
            [
                "Institutions account for over 90% of all forex trading volume — they move the markets",
                "Smart Money accumulates and distributes positions over days or weeks, not minutes",
                "Retail traders' stop losses are visible to brokers and often targeted by algorithms",
                "Institutional footprints appear on charts as order blocks, imbalances, and liquidity pools",
                "Aligning with Smart Money improves your win rate because you are trading with the dominant force",
            ],
            "Stop thinking about what you want the market to do. Instead, ask: where would an institution want to buy or sell? Look for areas where price consolidates before a strong move — that is likely where Smart Money entered."
        ),
        "order_blocks": (
            "An order block represents a specific price zone where institutional traders have placed a significant concentration of buy or sell orders. These zones appear as a cluster of candles where price consolidated before making a strong impulsive move. The logic is simple: if a large institution wants to buy millions of units, they cannot do so instantly without moving the price against themselves. Instead, they build a position over time within a range, creating what is visible on the chart as an order block. Once they have accumulated enough, they allow the price to move in their desired direction. A bullish order block is typically the last bearish candle immediately before a strong upward impulse. A bearish order block is the last bullish candle before a strong downward impulse. These zones act as powerful support and resistance because the institution is likely to defend their position by adding more at these levels.",
            [
                "Bullish order block: last down candle before a strong upward impulsive move",
                "Bearish order block: last up candle before a strong downward impulsive move",
                "Order blocks are most reliable on higher timeframes — 1H, 4H, and daily charts",
                "The best entries come when price retests the order block with confirmation (e.g., a rejection candle)",
                "Combine order blocks with trend direction for higher probability trades — trade blocks in the trend direction",
            ],
            "Go to the daily chart of EUR/USD. Find three clear order blocks — zones where price consolidated and then made a strong move. Mark them with horizontal boxes. Watch how price reacts when it returns to these zones. This is your new edge."
        ),
        "fair_value_gaps": (
            "A Fair Value Gap (FVG) is a price imbalance created when buying or selling pressure is so intense that price literally skips through a range without trading there. On a candlestick chart, an FVG appears between three consecutive candles where the wicks of the outer candles do not fully overlap with the wick of the middle candle. These gaps represent aggressive institutional order flow — the urgent need to execute large orders overcame the normal auction process. Because price left behind unfilled orders, these zones act like magnets. Price often returns to 'fill' the gap before continuing in the original direction. FVGs are categorized as bullish (gap to the upside) or bearish (gap to the downside). The higher the timeframe the FVG forms on, the more significant it is. A weekly FVG is far more important than a 5-minute FVG.",
            [
                "FVG forms when three consecutive candles have wicks that do not fully overlap — leaving a gap in price",
                "Price fills FVGs approximately 70% of the time before resuming the prevailing trend",
                "Higher timeframe FVGs (4H, daily, weekly) are significantly more reliable than lower timeframe ones",
                "Bullish FVG: middle candle's low is higher than the left candle's low and right candle's low",
                "FVGs are best traded in alignment with the overall trend — buy the gap in an uptrend",
            ],
            "Set up your 4-hour chart and mark all FVGs from the past two weeks. Then, on your 1-hour chart, watch how price behaves when it enters these zones. Look for a confirmation candle — a hammer or engulfing pattern — before entering."
        ),
        "liquidity_sweeps": (
            "A liquidity sweep (also called a stop hunt or fakeout) is a sharp price spike that takes out a cluster of stop-loss orders before reversing sharply. It is one of the most reliable institutional trading patterns. Here is how it works: retail traders place their stop losses just above recent highs (for shorts) or just below recent lows (for longs). Institutions can see where these clusters of liquidity are sitting. They push price into these zones, triggering all the stops, which provides them with the liquidity they need to enter or exit their own large positions at favorable prices. After sweeping liquidity, the price reverses because the institutional orders that caused the spike have been filled. The result is a sharp V-shaped or inverted V-shaped move that traps traders on both sides.",
            [
                "Liquidity pools form at recent swing highs, swing lows, and around round number levels",
                "Institutions need liquidity to enter and exit large positions — retail stops provide that liquidity",
                "A sweep is confirmed when price breaks a level but immediately reverses with strong momentum",
                "The best entries come on the reversal candle after the sweep — look for a strong rejection wick",
                "Combine sweeps with order blocks: a sweep into an order block is a very high-probability setup",
            ],
            "On the 15-minute chart, mark the most recent 5 swing highs and 5 swing lows. These are potential liquidity zones. Watch for price to spike through one of these levels and immediately reverse. That spike is your entry signal in the opposite direction."
        ),
        "break_of_structure": (
            "Break of Structure (BOS) — also called a Change in Character (CIC) or market structure shift — occurs when price breaks a key swing point, confirming that the current trend is continuing or a new trend is beginning. In an uptrend defined by higher highs and higher lows, a BOS happens when price breaks above the previous swing high. In a downtrend with lower highs and lower lows, a BOS happens when price breaks below the previous swing low. The BOS is distinct from a liquidity sweep in that the break is genuine — price does not immediately reverse back below the level. Instead, it continues in the breakout direction, signaling that the trend has strength. BOS is the foundational confirmation signal in Smart Money Concepts. No trade should be taken without first identifying a valid BOS in your trading direction.",
            [
                "A BOS in an uptrend = price breaks above the most recent swing high",
                "A BOS in a downtrend = price breaks below the most recent swing low",
                "A genuine BOS shows follow-through — the price continues in the breakout direction",
                "A failed BOS that reverses immediately is actually a liquidity sweep — trade the reversal",
                "The strongest trades come from a BOS that aligns with the higher timeframe trend",
            ],
            "On your 4-hour chart, identify the current trend. If it is up, mark the last swing high. When price breaks that high with a strong bullish candle, that is your BOS confirmation. Now drop to 1-hour to find an order block or FVG for your entry."
        ),
        "multi_timeframe": (
            "Multi-timeframe analysis is the practice of examining the same currency pair on multiple chart periods to build a complete market view. Each timeframe tells a different part of the story. The daily chart reveals the major trend and key structural levels that institutions care about. The 4-hour chart shows the medium-term trend and helps you identify high-quality order blocks and FVGs. The 1-hour or 15-minute chart allows you to pinpoint your entry with precision. The key rule is that higher timeframes dominate lower timeframes. If the daily chart is in a strong downtrend, you should only be looking for short opportunities on lower timeframes, even if the 15-minute chart looks bullish. This alignment dramatically increases your probability of success and prevents you from trading against the dominant force.",
            [
                "Higher timeframe (daily/weekly): determines the overall trend and key structural levels",
                "Medium timeframe (4H/1H): identifies order blocks, FVGs, and liquidity zones aligned with the trend",
                "Lower timeframe (15M/5M): provides precise entry timing and confirmation signals",
                "All timeframes must align for a high-probability trade — if the daily trend conflicts with your 15M setup, skip it",
                "The 'trend is your friend' applies to all timeframes, but the higher timeframe trend carries more weight",
            ],
            "Set up three monitors (or chart windows) with EUR/USD on daily, 4H, and 1H timeframes. Start every analysis session from the daily. Determine the trend. Drop to 4H for setup. Drop to 1H for entry. This three-step process alone will improve your trading."
        ),
        "vwap_explained": (
            "VWAP (Volume-Weighted Average Price) is a technical indicator that shows the average price at which a currency has traded throughout the current session, weighted by volume. It is calculated by adding up the value (price × volume) of all trades and dividing by total volume. VWAP is widely used by institutional traders to assess whether current price represents fair value. When price is above VWAP, it suggests buying pressure has dominated — price is 'premium' to the day's average. When price is below VWAP, selling pressure is dominant and price is at a 'discount'. Many institutions use VWAP as a benchmark, aiming to buy below VWAP and sell above it. For intraday traders, VWAP works as dynamic support and resistance. A rejection at VWAP with a confirmation candle is a tradeable signal.",
            [
                "VWAP resets at the start of each trading session and represents the day's average price",
                "Price above VWAP = bullish intraday bias; price below VWAP = bearish intraday bias",
                "VWAP acts as dynamic support in uptrends and dynamic resistance in downtrends",
                "A strong move away from VWAP (2-3 standard deviations) often reverts — mean reversion opportunity",
                "Combine VWAP with order blocks: a VWAP touch at an order block is a very strong confluence",
            ],
            "Add VWAP to your 15-minute chart. For one week, only take long trades when price is above VWAP and only take short trades when price is below VWAP. This single rule will eliminate many losing trades taken against the intraday momentum."
        ),
        "support_resistance": (
            "Support and resistance are the building blocks of all technical analysis. A support level is a price zone where buying interest is strong enough to overcome selling pressure, causing a decline to stop and reverse. A resistance level is where selling pressure overcomes buying interest, halting an advance. These levels form because market participants remember and react to prices where significant volume has previously traded. The more times a level has been tested, the stronger it becomes. When a support level is broken, it often becomes resistance, and vice versa — this is called role reversal. Psychological levels like round numbers (1.2000, 130.00) also act as natural support and resistance because traders place orders around these obvious prices. The most reliable levels are those that have been tested at least three times on the daily chart.",
            [
                "Support and resistance levels gain strength with each test — more touches = stronger level",
                "Role reversal: broken support becomes resistance, broken resistance becomes support",
                "Round numbers (1.3000, 110.00) act as psychological support and resistance zones",
                "The 200 EMA is a dynamic support/resistance level on all timeframes",
                "Always wait for a touch of a key level before entering — entering between levels reduces your edge",
            ],
            "On the daily chart, identify three clear support levels and three clear resistance levels for your pair. Draw them as horizontal lines. For one week, only trade when price touches one of these levels. You will immediately see the quality of your setups improve."
        ),
        "trend_identification": (
            "Trend identification is the skill of determining the market's current directional bias. An uptrend is defined by a series of higher highs and higher lows. A downtrend is defined by lower highs and lower lows. A sideways trend (range) occurs when price moves between horizontal support and resistance. The cardinal rule of trading is: the trend is your friend. Trading against the larger trend is a losing strategy over time. Multiple tools can help identify trends: moving averages (200 EMA, 50 SMA), trendlines connecting swing lows or swing highs, and ADX indicator to measure trend strength. The most reliable approach is to combine price action structure (higher highs/lower lows) with a moving average filter. When both agree on the direction, the trend is robust.",
            [
                "Uptrend = series of higher highs AND higher lows. Both conditions must be met",
                "Downtrend = series of lower highs AND lower lows. Both conditions must be met",
                "200 EMA on the 1-hour chart is an excellent trend filter — price above = uptrend, below = downtrend",
                "Trendlines drawn from at least two swing points help visualize the trend angle and direction",
                "In a strong trend, pullbacks to the moving average or trendline offer the best entry opportunities",
            ],
            "On your 1-hour chart, plot the 200 EMA. If price is above the 200 EMA with higher highs and higher lows, the trend is up — focus on long setups only. If below with lower highs and lower lows, focus on shorts. Trade this one rule for 20 trades. Record your results."
        ),
        "entry_exit_rules": (
            "Entry and exit rules transform trading from gambling into a business. An entry rule defines the exact conditions that must be met before you click the buy or sell button. An exit rule defines precisely when you close the trade — both for profit and for loss. Without these rules, every trade becomes an emotional decision driven by fear and greed. A complete entry rule might be: 'Enter long when price creates a BOS on the 1-hour chart, retests a bullish order block on the 4-hour chart, and shows a bullish engulfing candle on the 15-minute chart.' An exit rule might be: 'Exit 50% at 1:1 risk-to-reward, move stop to breakeven, trail remaining position by 20 EMA.' The specificity of these rules removes ambiguity and makes your trading mechanical.",
            [
                "Entry rules must be specific, objective, and written down before the trade",
                "Exit rules should include: stop loss level, first take profit, and final take profit",
                "A trade checklist forces discipline — print it and tick every box before entering",
                "Multiple timeframes in your entry rules increase probability but require patience",
                "Review and refine your rules every 50 trades based on what is working and what is not",
            ],
            "Write your complete entry and exit rules on a single sheet of paper. Use the format: 'IF [conditions], THEN [action].' Tape this paper next to your monitor. Do not take a single trade until every condition on your checklist is met. This is non-negotiable."
        ),
        "position_sizing": (
            "Position sizing is the process of determining how many units (lots) to trade based on your account size, risk tolerance, and the distance to your stop loss. It is the most critical risk management skill because it keeps you in the game during losing streaks. The golden rule is to risk no more than 1-2% of your account on any single trade. The formula is: Position Size = (Account Balance × Risk %) / (Stop Loss Distance in Pips × Pip Value). If you have a $10,000 account and risk 1% ($100) on a trade with a 20-pip stop loss on EUR/USD where each pip is worth $10 (standard lot), you can trade 0.5 standard lots. This formula ensures that your risk stays constant regardless of where your stop loss is placed. Proper position sizing means a string of 10 consecutive losses only costs you 10-20% of your account — not a blown account.",
            [
                "Never risk more than 1% per trade until you have been profitable for 6 months. 2% maximum for experienced traders",
                "Calculate lot size = (Account × Risk%) / (Stop in pips × Pip value per lot)",
                "Consistent position sizing (same % risk every trade) stabilizes your equity curve",
                "Increasing position size after wins (compounding) accelerates growth, but do it gradually",
                "Never increase position size to 'make back' losses — this is revenge sizing and destroys accounts",
            ],
            "Use a free position size calculator (babypips.com or myfxbook.com) before every trade for one month. Input your account balance, risk percentage (1%), stop loss in pips, and the pair. The calculator tells you your exact lot size. This removes all guesswork."
        ),
        "stop_loss_placement": (
            "Stop loss placement is arguably more important than your entry. A stop loss is an order that automatically closes your position at a predetermined price if the market moves against you. Its purpose is to limit your loss on any single trade to an acceptable amount. The key challenge is placing your stop at a level that gives the trade enough room to breathe while still protecting your capital. Place it too tight, and you will be stopped out by normal market noise. Place it too wide, and one loss could wipe out many wins. The best approach is to place stops just beyond the last swing low (for longs) or swing high (for shorts), adding a small buffer of 5-10 pips to avoid being picked off by random spikes. Using the ATR indicator to set your stop distance (e.g., 1.5× ATR) adjusts automatically to market volatility.",
            [
                "Place stops below the most recent swing low for longs, above the most recent swing high for shorts",
                "Add a 5-10 pip buffer to your stop to avoid being taken out by wicks and random noise",
                "Use ATR to set dynamic stop distances — 1.5× to 2× ATR gives the market room to breathe",
                "Never move your stop loss wider after entering — only move it tighter (toward your entry) or not at all",
                "Your stop loss level should be determined BEFORE you enter the trade, not after",
            ],
            "Before each trade for the next two weeks, write down exactly where you will place your stop and why. The reason should be specific: 'The stop goes 10 pips below the last swing low because if price breaks that level, my bullish thesis is invalid.'"
        ),
        "take_profit_strategy": (
            "A take profit (TP) order closes your trade at a predetermined profit level. While stop losses are mandatory, take profits are more flexible — you can use trailing stops or partial closes. However, having a clear TP target prevents a common psychological error: letting a winning trade turn into a loser because you got greedy. A robust take profit strategy involves multiple targets. Set TP1 at a 1:1 risk-to-reward ratio. Close 50% of your position there and move your stop loss to breakeven on the remaining 50%. This guarantees that on this trade, at worst you break even. Set TP2 at a 1:2 or 1:3 ratio and let the remaining position ride with a trailing stop. This structure gives you the best of both worlds: frequent small wins from TP1 and occasional large wins from TP2.",
            [
                "Set TP1 at 1:1 risk-to-reward — close 50% of position, move stop to breakeven",
                "Set TP2 at 1:2 or 1:3 risk-to-reward — let the remaining position run",
                "Use a trailing stop after TP1 is hit to capture extended moves without giving back profits",
                "Moving your stop to breakeven at TP1 ensures every winning trade ends with at least a scratch",
                "Multiple TP levels reduce the emotional pressure of picking exactly the top or bottom",
            ],
            "Before entry, mark two TP levels on your chart: TP1 at the first logical resistance (for longs) and TP2 at the next major resistance. Set limit orders for both. When TP1 hits, manually move your stop to entry price. Let the rest run."
        ),
        "risk_reward_ratio": (
            "Risk-to-reward ratio (RRR) compares how much you stand to lose to how much you stand to gain on a trade. If you risk 20 pips to make 60 pips, your RRR is 1:3. RRR is the mathematical foundation of profitable trading. Here is why it matters: you do not need to be right most of the time to make money. With a 1:3 RRR, you can be right only 30% of the time and still be profitable. With a 1:1 RRR, you need to be right over 50% of the time just to break even. The key insight is that RRR is within your control — you choose where to place your stop and your target. Most retail traders lose money because they take trades with poor RRR (1:1 or worse) and let their winners run too small while their losses run too large. Flipping this around — small stops, large targets — is the single biggest change you can make to your profitability.",
            [
                "Minimum acceptable RRR should be 1:2. Ideally target 1:3 or higher",
                "A 40% win rate with 1:3 RRR = 20% return per 100 trades (net positive)",
                "A 60% win rate with 1:1 RRR = 10% return per 100 trades (net positive, but less)",
                "Calculate RRR before entry: (Target Pips - Entry Pips) / (Entry Pips - Stop Pips)",
                "If the RRR does not meet your minimum standard, skip the trade — no exceptions",
            ],
            "For the next 30 trades, do not enter any trade where the potential profit is less than double the potential loss. Use a hard rule: RRR must be ≥ 1:2 or you do not take the trade. Track how this changes your overall profitability."
        ),
        "kelly_criterion": (
            "The Kelly Criterion is a mathematical formula developed by John Kelly at Bell Labs that determines the optimal fraction of your capital to risk on each trade to maximize long-term growth. The formula is: Kelly % = W - (1 - W) / R, where W is your win rate and R is your average risk-to-reward ratio. For example, if you have a 50% win rate and a 1:2 RRR, your Kelly % = 0.5 - 0.5 / 2 = 0.25, meaning you should risk 25% of your account per trade for maximum growth. This sounds aggressive because it is — the full Kelly value maximizes growth but also creates enormous volatility. Professional traders use 'fractional Kelly,' risking only 25% to 50% of the Kelly value. You need at least 100 trades of data to calculate meaningful win rate and RRR. Kelly protects you from overbetting when your edge is small and helps you properly scale when your edge is large.",
            [
                "Kelly % = W - (1 - W) / R. W = win rate (decimal), R = average risk-to-reward ratio",
                "If Kelly is negative, your strategy has negative expectancy — stop trading it immediately",
                "Full Kelly maximizes growth but creates extreme drawdowns — use 25% fractional Kelly in practice",
                "You need minimum 100 trades to calculate a statistically meaningful Kelly percentage",
                "Recalculate Kelly every month based on your rolling 100-trade window",
            ],
            "Track your last 100 trades in a spreadsheet: win or loss, and the RRR of each. Calculate your win rate and average RRR. Plug these into the Kelly formula. Multiply the result by 0.25. This is your suggested risk % per trade. Use it for the next 50 trades."
        ),
        "trading_psychology": (
            "Trading psychology is the study of how your emotions and mental state influence your trading decisions. It is widely accepted among professional traders that psychology is more important than strategy. You can have the best strategy in the world, but if fear prevents you from taking the trade or greed makes you hold a loser, you will not make money. The two primary emotional enemies are fear and greed. Fear causes you to enter too late, exit too early, or skip high-probability setups entirely. Greed causes you to overtrade, increase position sizes beyond your risk plan, and refuse to close winners until they turn into losers. The most effective tool for overcoming these emotions is a trading journal. By writing down what you felt during each trade, you start to see patterns. Once you see a pattern, you can create rules to neutralize it.",
            [
                "Fear makes you exit winners early and avoid entering trades that meet your criteria",
                "Greed makes you overtrade, increase risk, and hold trades past your take profit target",
                "A trading journal with emotional notes is the most effective psychology tool",
                "Breathing exercises and stepping away from the screen reduce emotional reactivity",
                "Acceptance of losses as a normal part of trading removes their emotional sting",
            ],
            "Start a trading journal today. For every trade, write: (1) How did I feel before entry? (2) How did I feel when the trade was running? (3) How did I feel after exit? After 30 trades, review your journal. You will see your emotional patterns clearly."
        ),
        "fomo_explained": (
            "FOMO — Fear Of Missing Out — is the emotional state that occurs when you see a currency pair making a strong move and feel a desperate urge to join the move before it 'gets away.' It is one of the most dangerous emotions in trading because it makes you abandon all your rules. You enter without checking your entry criteria. You skip proper position sizing. You ignore the risk-to-reward ratio. The result is almost always buying the top of a rally or selling the bottom of a decline. FOMO is driven by the fear that you are missing a once-in-a-lifetime opportunity. But the forex market moves 24 hours a day, 5 days a week. There are literally thousands of trading opportunities every week. No single move is worth abandoning your rules. The antidote to FOMO is acceptance: you cannot catch every move, and trying to is the fastest path to blowing up your account.",
            [
                "FOMO causes you to abandon your trading plan and enter without proper confirmation",
                "A big move you missed is not lost money — it was never yours, and another opportunity will come",
                "Chasing price almost always results in buying the high or selling the low",
                "The market has been running for decades and will continue — there is no such thing as 'the one that got away'",
                "The best cure for FOMO is to reduce your chart time and trust your written trading plan",
            ],
            "The next time you feel FOMO, do the opposite of what your emotions say. Close your chart, step away for 15 minutes, and breathe. If the setup still looks valid after 15 minutes with a calm mind, then and only then consider entering. Most FOMO trades look terrible after a short break."
        ),
        "revenge_trading": (
            "Revenge trading is the destructive cycle that begins after a loss. The logic goes: 'I just lost $200. I need to get it back. I will take a bigger trade to recover fast.' This is the single fastest way to blow up a trading account. When you are emotional after a loss, your judgment is severely impaired. You are not seeing the market clearly — you are seeing a target for your anger. The loss becomes personal, and you feel the need to 'win' against the market. But the market does not know you exist. It is a neutral system of global currency flows. Taking a larger position after a loss compounds the problem: if you lose again, the damage is magnified. A single revenge trading session can undo months of disciplined work. The only winning move is to stop. Accept the loss as a cost of doing business. Come back tomorrow with a clear head.",
            [
                "Revenge trading turns a small, acceptable loss into a catastrophic drawdown",
                "After a loss, your brain is flooded with cortisol and adrenaline — you cannot make rational decisions",
                "Increasing position size to 'win back' losses is gambling, not trading",
                "The market does not owe you anything — losses are a normal part of the business",
                "A pre-committed rule: if you lose more than 3% in a day, stop trading completely",
            ],
            "Create a hard rule today: if you have a losing trade, you must wait at least 60 minutes before taking the next trade. If you lose 3% of your account in a single day, you are done for the day. Write this rule down. Tape it to your monitor. Follow it without exception."
        ),
        "patience_in_trading": (
            "Patience is the ability to wait for the right opportunity rather than forcing a trade in suboptimal conditions. In a world of instant gratification, patient trading is countercultural — and that is exactly why it is so profitable. The market offers high-probability setups only 10-20% of the time. The rest of the time, price moves in random, choppy patterns that will punish anyone who tries to trade them. Patient traders understand that being in cash is a valid position. They wait for the confluence of multiple factors — trend alignment, an order block or FVG, a confirmation candle, a favorable risk-to-reward ratio — before acting. They are willing to watch 50, 100, or 200 candles without taking a trade. This patience is rewarded with trades that have a much higher win rate and much lower stress. The best trades often feel like the market is handing you money on a silver platter because the setup is so obvious.",
            [
                "High-probability setups occur only 10-20% of the time — most of trading is waiting",
                "Cash is a position — being out of the market preserves capital and mental clarity",
                "Waiting for confluence (multiple confirming factors) drastically improves your win rate",
                "The best trades feel 'obvious' because all the pieces align perfectly",
                "If you are unsure about a trade, that is your answer — uncertainty means sit out",
            ],
            "For one week, aim to take no more than three trades total. This scarcity mindset will force you to only choose the absolute best setups. Quality over quantity. At the end of the week, compare your results to your normal trading frequency."
        ),
        "building_discipline": (
            "Discipline is the ability to execute your trading plan exactly as designed, regardless of how you feel in the moment. It is the bridge between knowing what to do and actually doing it. Every trader knows they should use a stop loss. Not every trader places one on every trade. That gap — between knowledge and action — is closed by discipline. Discipline is not a trait you are born with; it is a skill you build through repetition. Every time you follow your plan, even when it is hard, you strengthen your discipline muscle. Every time you skip a trade that does not meet your criteria, you strengthen it. A powerful tool for building discipline is a pre-trade checklist. By making your rules concrete and checking them off like a pilot before takeoff, you remove the opportunity for emotions to override your process.",
            [
                "Discipline is doing what your plan says, not what your emotions want in the moment",
                "A physical pre-trade checklist forces discipline by making rules non-negotiable",
                "Discipline is built through tiny consistent actions, not grand heroic gestures",
                "Track your 'discipline score' — what percentage of trades followed all your rules",
                "The goal is to follow the plan perfectly, not to be right on every trade",
            ],
            "Create a one-page trading plan. Print it. Every morning, read it aloud before your session. After each day, rate your discipline from 1-10 based on how well you followed the plan, not on P&L. Aim for a 10 every day regardless of whether you made or lost money."
        ),
        "correlation_trading": (
            "Currency correlation measures how the price movements of two currency pairs relate to each other over time. The correlation coefficient ranges from -1 to +1. A value of +1 means the pairs move in perfect lockstep. A value of -1 means they move in perfect opposition. A value of 0 means no relationship. Understanding correlation prevents you from accidentally taking on more risk than you realize. For example, buying EUR/USD and buying GBP/USD might seem like two separate trades, but these pairs have a correlation of about +0.80. You are effectively doubling your exposure to the USD side of the trade. Similarly, buying EUR/USD and buying USD/CHF (correlation of about -0.85) cancels out your exposure — you are essentially hedged. Correlation also helps with diversification: by trading uncorrelated pairs, you spread your risk across independent market movements.",
            [
                "EUR/USD and GBP/USD: strong positive correlation (+0.80) — trading both doubles USD exposure",
                "EUR/USD and USD/CHF: strong negative correlation (-0.85) — buying both creates a hedge",
                "USD/JPY and gold (XAU/USD): often negative correlation — risk-on vs risk-off relationship",
                "Correlation is not static — it changes during market stress and shifts in economic conditions",
                "Checking correlation before entering multiple positions prevents unintended risk concentration",
            ],
            "Use a free correlation calculator (myfxbook.com or oanda.com) to check current correlations before your trading session. If you plan to trade multiple pairs, ensure you are not accidentally overexposed to the same currency. Diversification works in forex too."
        ),
        "news_trading": (
            "News trading involves taking positions around major economic data releases such as Non-Farm Payrolls (NFP), Consumer Price Index (CPI), Gross Domestic Product (GDP), and central bank interest rate decisions. These events cause the most significant volatility spikes in the forex market. A single NFP release can move EUR/USD by 50-100 pips in seconds. The challenge is that news trading is extremely risky for beginners. The spreads widen dramatically, slippage is common, and price can spike in both directions within a few bars before establishing a direction. The safest approach is to avoid trading during the first 15 minutes after a release. Let the initial volatility settle, identify the direction the market has decided on, and then trade in that direction using normal technical analysis on the post-news price action. An economic calendar (Forex Factory, Investing.com) is essential — you must know when every major release is scheduled.",
            [
                "Major news events are scheduled — always check an economic calendar at the start of each week",
                "NFP (first Friday of every month), CPI, and central bank decisions are the highest-impact events",
                "Spreads can widen 10-20× normal levels during news — your entry will cost more",
                "The first 15 minutes after a release are chaotic — let the market find its direction first",
                "Post-news trends often develop in the direction of the initial breakout — trade the follow-through",
            ],
            "Bookmark the Forex Factory economic calendar. Every Sunday, review the upcoming week's high-impact events. For your first three months, simply close all positions 30 minutes before each high-impact event and re-enter 30 minutes after. This keeps you safe while you learn."
        ),
        "yield_curve_impact": (
            "The yield curve is a graph that plots the interest rates of government bonds (typically US Treasuries) across different maturities — from 1 month to 30 years. A normal yield curve slopes upward: longer-term bonds pay higher yields to compensate for inflation and time risk. An inverted yield curve (short-term rates higher than long-term rates) has preceded every US recession in the last 60 years. A steepening yield curve (long rates rising faster than short rates) signals economic growth expectations. A flattening yield curve signals economic pessimism. For forex traders, the yield curve directly impacts currency values through interest rate expectations. If a country's yield curve is steepening while another's is flattening, the steepening country's currency is likely to strengthen as capital flows toward higher yields. The 2-year vs 10-year Treasury spread is the most watched yield curve metric.",
            [
                "Normal yield curve: long rates > short rates = healthy economic expectations",
                "Inverted yield curve: short rates > long rates = recession warning, typically weakens growth currencies",
                "Steepening curve: long rates rising faster = bullish for the currency",
                "Flattening curve: long rates falling relative to short rates = bearish for the currency",
                "Check the 2Y-10Y Treasury spread weekly — this single metric summarizes market expectations",
            ],
            "Every Monday, check the US 2-year vs 10-year Treasury spread on Investing.com or Bloomberg. If the spread is negative (inverted), favor safe-haven currencies (USD, JPY, CHF). If positive and steepening, favor growth currencies (AUD, NZD, emerging market currencies)."
        ),
        "sentiment_analysis": (
            "Sentiment analysis measures the overall attitude of market participants toward a currency, pair, or market. The core principle is contrarian: when the crowd is overwhelmingly bullish, there may be few buyers left to push price higher, making a reversal likely. When the crowd is overwhelmingly bearish, most sellers have already sold, potentially exhausting the selling pressure. Several tools provide sentiment data: the COT (Commitment of Traders) report published weekly by the CFTC shows how large speculators and commercial traders are positioned in futures markets. Retail sentiment tools from brokers show the long/short ratio of retail clients. When retail sentiment reaches extremes (80%+ in one direction), it is often a reliable contrarian signal. The COT report is especially valuable because it shows what Smart Money (commercials) and dumb money (large speculators) are doing.",
            [
                "COT report: commercials = Smart Money (banks, institutions), large speculators = trend-following funds",
                "When commercial traders are heavily long and speculators are heavily short, it is a bullish signal",
                "Retail sentiment of 80%+ long often coincides with market tops",
                "Sentiment is most useful as a warning signal, not a standalone entry trigger",
                "Combine sentiment with technical analysis: extreme sentiment + a key level = high-probability reversal",
            ],
            "Visit myfxbook.com/forex-market/sentiment every Friday. Check the retail long/short percentage on your main trading pairs. If any pair shows 80%+ retail bias in one direction, add it to your watchlist. Look for reversal signals on the daily chart."
        ),
        "building_your_system": (
            "A trading system is a complete, rule-based approach to the markets that governs every aspect of your trading. It answers six questions: What do I trade? When do I enter? Where is my stop? Where is my target? How much do I risk? When do I stop trading for the day? A good system removes all subjectivity from trading. Every condition is defined in black and white. You do not have to decide in the moment because you already decided when you designed the system. The three phases of building a system are: design (write the rules clearly), backtest (test on at least 6 months of historical data, minimum 100 trades), and forward test (trade on demo for at least 50 more trades). Only after passing all three phases should you risk real money. The best system is the one you can follow consistently. Overly complex systems fail because traders cannot execute them perfectly. Simple rules executed with discipline will outperform brilliant strategies applied inconsistently.",
            [
                "A complete system covers: market selection, entry rules, exit rules, risk management, and daily routine",
                "Backtest on at least 6 months of data with 100+ trades to validate your edge",
                "Forward test on demo for 50+ trades before going live with real capital",
                "Simplicity wins — a 5-rule system you follow perfectly beats a 20-rule system you ignore",
                "Your system is never finished — review and refine it every 100 trades based on data",
            ],
            "Write your trading system on a single piece of paper. Use bullet points. Include: what pairs you trade, what timeframes, your exact entry conditions, stop and target rules, and your max daily loss limit. Start demo trading this system today. Commit to 100 demo trades before funding a live account."
        ),
    }
    data = topics.get(topic, topics["what_is_forex"])
    lesson, points, action = data
    points_text = "\n".join(f"{i+1}. {p}" for i, p in enumerate(points))
    return (
        f"📚 DAY {day_num}/30 — {title}\n\n"
        f"━━━ LESSON ━━━\n"
        f"{lesson}\n\n"
        f"━━━ KEY POINTS ━━━\n"
        f"{points_text}\n\n"
        f"━━━ ACTION ITEM ━━━\n"
        f"{action}\n\n"
        f"Join FREE: @omnibrainsignals_free\n"
        f"Join VIP: @omnibrainsignals_vip"
    )


def _youtube_en(day_num, topic, title):
    topics = {
        "what_is_forex": (
            "Did you know the forex market moves over $7.5 trillion every single day? That is more than all the world's stock markets combined.",
            "But here is the thing: most retail traders lose money because they jump in without understanding the basics. Currencies always trade in pairs — EUR/USD, GBP/USD — and you are always buying one while selling the other.",
            "The key is to start with the major pairs, use a demo account first, and never trade with money you cannot afford to lose. Follow for more daily lessons and start your trading journey the right way.",
        ),
        "what_is_pip": (
            "A pip is the smallest price movement in forex. For EUR/USD, one pip is 0.0001. For USD/JPY, it is 0.01.",
            "Every profit and loss you make is measured in pips. If you buy EUR/USD at 1.1050 and it moves to 1.1070, you just made 20 pips. On a standard lot, that is $200.",
            "But here is the real tip: always calculate pip value before you enter, not after. Use a pip calculator. Know exactly what each pip is worth in your account currency before risking a cent.",
        ),
        "what_is_leverage": (
            "Leverage lets you control $100,000 with just $1,000. Sounds amazing, right?",
            "But here is the catch: it amplifies losses just as much as gains. A 1% move against you with 1:100 leverage wipes out your entire account. Professional traders use low leverage — typically 1:10 or less — and focus on position sizing instead.",
            "The secret is simple: use less leverage than your broker offers. Your account will last longer, and your stress levels will drop dramatically. Protect your capital first.",
        ),
        "what_is_spread": (
            "The spread is the cost of every trade you take. It is the difference between the buy price and the sell price.",
            "If EUR/USD has a 2-pip spread, you start every trade 2 pips in the red. Spreads vary wildly — they are tight during London sessions and wide during news events.",
            "Here is the pro tip: trade major pairs during the London-New York overlap when spreads are tightest. Check your broker's spread before every trade. If the spread eats more than 20% of your target, wait for a better opportunity.",
        ),
        "market_sessions": (
            "The forex market runs 24 hours through four sessions: Sydney, Tokyo, London, and New York.",
            "Most traders do not realize that the session you trade completely changes your results. The Asian session is slow and range-bound. London is fast and volatile. The New York session brings huge moves during US data releases.",
            "The golden window is the London-New York overlap from 12:00 to 16:00 GMT — this is when volume and volatility peak. Pick one session, master its rhythm, and stop trading around the clock.",
        ),
        "what_is_smart_money": (
            "Institutions move the markets — not retail traders like you and me. Banks, hedge funds, and central banks control 90% of forex volume.",
            "Smart Money Concepts help you follow their footprints. When you see price consolidate in a tight range and then explode upward, that is an institution accumulating positions. When you see a sudden spike through a high that immediately reverses, that is a liquidity trap for retail traders.",
            "Stop fighting the institutions and start trading with them by learning to read order blocks, FVGs, and liquidity sweeps.",
        ),
        "order_blocks": (
            "Order blocks are where the big money places their trades. A bullish order block is the last red candle before a powerful upward move.",
            "A bearish order block is the last green candle before a sharp decline. These zones act like magnets — price returns to them before continuing. Here is how to use them: go to your daily chart, find an order block, and wait for price to retest it.",
            "When you see a rejection candle at that level, that is your entry. Combine this with the overall trend, and you have a powerful edge in the markets.",
        ),
        "fair_value_gaps": (
            "Fair Value Gaps are price imbalances that institutions leave behind when they move the market aggressively.",
            "You can spot them when three consecutive candles have wicks that do not overlap — there is a 'gap' in price. Here is the key insight: price returns to fill these gaps about 70% of the time.",
            "Mark the FVGs on your 4-hour chart. When price enters a gap zone, look for a reversal candle. Enter in the direction of the original move. Just remember — higher timeframe gaps are way more reliable than 5-minute gaps.",
        ),
        "liquidity_sweeps": (
            "A liquidity sweep happens when price spikes through a key level to trigger stop losses, then reverses immediately.",
            "Institutions need liquidity to enter their large orders, and retail stop losses are the perfect source. Here is what to watch for: price breaks above a recent high, but instead of continuing, it reverses hard with a long wick. That wick is the sweep.",
            "Your move? Enter in the opposite direction with a stop beyond the wick. The key is patience — wait for the reversal candle to close before entering. Do not try to catch a falling knife.",
        ),
        "break_of_structure": (
            "A Break of Structure confirms the trend is alive and well. In an uptrend, a BOS happens when price breaks above the previous high.",
            "In a downtrend, it breaks below the previous low. The key difference between a BOS and a fakeout is follow-through. A real BOS keeps moving in the breakout direction. A fakeout reverses immediately — that is actually a liquidity sweep, not a BOS.",
            "The best trades combine a BOS with an order block retest. First confirm the trend with a BOS, then wait for a pullback to an order block for your entry.",
        ),
        "multi_timeframe": (
            "Looking at just one timeframe is like looking at the world through a keyhole. Multi-timeframe analysis gives you the full picture.",
            "Start on the daily chart to identify the major trend. Drop to the 4-hour to find your setup — an order block or FVG that aligns with the daily trend. Then drop to the 1-hour for your precise entry.",
            "If all three timeframes agree, your trade has a much higher probability of success. The most common mistake is trading a 15-minute setup that goes against the daily trend. Always respect the higher timeframe first.",
        ),
        "vwap_explained": (
            "VWAP is the volume-weighted average price of a currency throughout the trading session. Think of it as the day's 'fair price.'",
            "When price is above VWAP, buyers are in control. When below, sellers are in control. Institutions use VWAP as a benchmark, and so should you.",
            "Add VWAP to your 15-minute chart. If price is above VWAP, only look for longs. If below, only look for shorts. If price is far away from VWAP, expect a reversion back to it. Combine VWAP with your support and resistance levels for even better entries.",
        ),
        "support_resistance": (
            "Support and resistance are the most basic and most reliable tools in trading. Support is where buyers step in. Resistance is where sellers step in.",
            "The more times a level is tested, the stronger it becomes. When price breaks a level, that level often flips its role — support becomes resistance, resistance becomes support.",
            "Draw your key levels on the daily chart. Wait for price to approach one of them. Look for confirmation — a rejection candle, a divergence, or a volume spike. Do not just buy at support blindly; wait for evidence that the level is holding.",
        ),
        "trend_identification": (
            "The trend is your friend — until it is not, but most of the time it is. Identifying the trend is simple: higher highs and higher lows equals an uptrend.",
            "Lower highs and lower lows equals a downtrend. If you are getting neither, the market is ranging. The 200 EMA on the 1-hour chart is a great trend filter. Price above the 200 EMA means focus on longs. Price below means focus on shorts.",
            "Draw trendlines connecting swing lows in an uptrend or swing highs in a downtrend. A clean trendline with multiple touches is strong. Trade with the trend and you will stop fighting the market.",
        ),
        "entry_exit_rules": (
            "Without rules, trading is just gambling. Your entry rules define exactly when you click buy or sell. Your exit rules define when you take profit or cut losses.",
            "Be specific. Instead of 'buy when it looks bullish,' say 'buy when price creates a BOS on 1H, retests a 4H order block, and forms a bullish engulfing candle on 15M.' Write these rules down. Print them. Put them on your wall.",
            "A trade checklist removes emotional decisions. Before every trade, tick through your checklist item by item. If one condition is missing, you do not take the trade. Period.",
        ),
        "position_sizing": (
            "Position sizing is the most important risk management tool you have. The formula is simple: how much money can you lose on this trade?",
            "Never risk more than 1% of your account on a single trade. If you have $10,000, your max loss per trade is $100. Use a position size calculator to figure out exactly how many lots to trade based on your stop loss distance.",
            "This ensures you risk the same dollar amount on every trade, regardless of how far your stop is. Consistency in position sizing is what keeps you alive during losing streaks. Survival comes first, profits come second.",
        ),
        "stop_loss_placement": (
            "Every trade needs a stop loss. No exceptions. The question is where to put it.",
            "Place your stop just beyond the last swing low if you are long, or just beyond the last swing high if you are short. Then add a 5-10 pip buffer to avoid being taken out by market noise.",
            "Here is the golden rule: once your stop is placed, never move it further away. You can move it tighter to lock in profits, but widening your stop is the first step toward a blown account. Set your stop before you enter the trade.",
        ),
        "take_profit_strategy": (
            "Taking profit is harder than it looks. The best strategy is to use multiple targets.",
            "Set your first target at 1:1 risk-to-reward. Close half your position there and move your stop to breakeven. Now the trade is risk-free. Set your second target at 1:2 or 1:3 risk-to-reward and let the rest run.",
            "Use a trailing stop after TP1 to capture any additional movement. This approach gives you the best of both worlds: frequent small wins from TP1 and occasional big wins from TP2. Do not watch a winner turn into a loser because you got greedy.",
        ),
        "risk_reward_ratio": (
            "Risk-to-reward ratio is the math of trading. If you risk 20 pips to make 60, your RRR is 1:3.",
            "The beauty of RRR is that you do not need to be right most of the time. With a 1:3 RRR, you only need to be right 25% of the time to break even. With a 1:2 RRR, you need to be right 33%.",
            "Your minimum standard should be 1:2. If a trade does not offer at least twice the reward as the risk, skip it. There is always another setup. Do not chase small rewards with big risks.",
        ),
        "kelly_criterion": (
            "The Kelly Criterion tells you exactly how much to risk per trade. The formula: Kelly % = Win Rate - (Loss Rate / RRR).",
            "If your win rate is 50% and your RRR is 1:2, Kelly says risk 25% of your account. That is way too aggressive — full Kelly will have your account swinging wildly. Smart traders use fractional Kelly: take 25% of the Kelly value.",
            "Track 100 trades, calculate your Kelly, and let the math guide your risk decisions. Use 1-2% per trade as a safer alternative while you build track record.",
        ),
        "trading_psychology": (
            "Your mindset matters more than your strategy. Fear makes you exit winners too early and skip good trades. Greed makes you overtrade and hold losers too long.",
            "The best tool for managing psychology is a trading journal. Write down how you feel before, during, and after every trade. Review your journal weekly. You will start seeing patterns — like how you always get scared after two wins in a row.",
            "Once you see the pattern, you can create a rule to counteract it. Trading is 80% psychology and 20% strategy. Work on your mind.",
        ),
        "fomo_explained": (
            "FOMO kills more accounts than bad strategies. Here is how it happens: you see a pair making a big move and feel pressure to 'catch it.'",
            "You abandon your rules and jump in. Then price reverses, and you are left holding the bag. The truth is, the market has been running for decades. There are thousands of trades every week.",
            "The next time you feel FOMO, close your laptop and walk away for 15 minutes. If the setup still looks good after you calm down, consider it. Most FOMO trades look terrible after a short break.",
        ),
        "revenge_trading": (
            "Revenge trading is the fastest way to blow up an account. You lose $100, so you take a $200 trade to get it back.",
            "Then you lose that too, so you take a $500 trade. Before you know it, your account is gone. After a loss, your brain is not thinking clearly. You are emotional. You are angry. The market is neutral — it does not care about your P&L.",
            "The only winning move after a loss is to stop. Step away. Come back tomorrow. Create a hard rule: if you lose 3% of your account in one day, you are done for the day. Follow it without exception.",
        ),
        "patience_in_trading": (
            "The best traders spend 90% of their time waiting. High-probability setups do not come every hour. They come a few times a week at most.",
            "The rest of the time, the market is random noise that will chew up impatient traders. Cash is a position. Being out of the market preserves your capital for the next real opportunity.",
            "If you feel the urge to trade, ask yourself: does this setup meet every condition in my plan? If the answer is no, walk away. The market will still be there tomorrow.",
        ),
        "building_discipline": (
            "Discipline is doing what your plan says even when you do not feel like it. It is the difference between knowing and actually doing.",
            "Discipline is built through small, consistent actions. Print your trading plan. Read it before every session. Create a pre-trade checklist and go through it for every single trade.",
            "Rate your discipline on a scale of 1 to 10 at the end of every day. The goal is not to make money every day. The goal is to follow your plan perfectly. If you do that, the money takes care of itself.",
        ),
        "correlation_trading": (
            "Currency correlation tells you how pairs move in relation to each other. EUR/USD and GBP/USD move together. EUR/USD and USD/CHF move opposite.",
            "If you buy both EUR/USD and GBP/USD, you are essentially doubling your USD risk. Not smart. Always check correlation before taking multiple trades.",
            "Use a correlation tool to check before your session. It takes 30 seconds and can save you from unintended risk. If pairs are correlated, choose the one with the better setup.",
        ),
        "news_trading": (
            "News events like NFP and CPI can move the market 100 pips in seconds. They are the most volatile times in forex.",
            "For beginners, the rule is simple: do not trade during news. Spreads widen 10x, slippage is common, and price can spike both ways before trending.",
            "Mark the news times on your calendar. Close all positions 30 minutes before. Wait 30 minutes after for the chaos to settle. Then look for the new trend. Learn before you earn.",
        ),
        "yield_curve_impact": (
            "The yield curve predicts where the economy is heading. A normal curve slopes up — long-term bonds pay more. An inverted curve signals recession.",
            "For forex traders, this is gold. An inverted yield curve in the US means the dollar may weaken as rate cuts become likely. A steepening curve means growth expectations are rising.",
            "Check the 2-year versus 10-year Treasury spread every week. This single number tells you what the smartest money in the world expects from the economy.",
        ),
        "sentiment_analysis": (
            "Sentiment analysis tells you what everyone else is doing — so you can do the opposite. When 80% of retail traders are long on EUR/USD, who is left to buy?",
            "Use the COT report to see what institutions are doing. Use retail sentiment tools to see the crowd. The signal is strongest when commercials are long and retail is short.",
            "Sentiment alone is not a trade signal. But combined with a key support or resistance level, it is a powerful warning that a reversal may be coming.",
        ),
        "building_your_system": (
            "You have made it to day 30. Now it is time to put it all together into one complete trading system.",
            "Your system needs six things: what to trade, when to enter, where to put your stop, where to set your target, how much to risk, and when to stop for the day. Write it all on one page. Backtest it on 6 months of data. Demo trade it for 50 more trades.",
            "The best system is simple. Simple enough that you can follow it every day without thinking. Most traders overtrade because they use complex systems they cannot execute. You will not make that mistake.",
        ),
    }
    data = topics.get(topic, topics["what_is_forex"])
    hook, explanation, cta = data
    return (
        f"🎬 YOUTUBE SHORT — DAY {day_num}\n\n"
        f"HOOK (0-5s):\n"
        f"\"{hook}\"\n\n"
        f"EXPLANATION (5-45s):\n"
        f"\"{explanation}\"\n\n"
        f"CTA (45-60s):\n"
        f"\"{cta}\""
    )


def generate_day(day_num, target_languages=None):
    """Generate all content for a specific day in specified languages."""
    engine = get_engine()

    if target_languages is None:
        target_languages = list(LANGUAGES.keys())

    day_info = next((d for d in DAYS if d[0] == day_num), None)
    if not day_info:
        return {'error': f'Day {day_num} not found'}

    day_num, topic_slug, title = day_info

    insta_en = _instagram_en(day_num, topic_slug, title)
    tele_en = _telegram_en(day_num, topic_slug, title)
    yt_en = _youtube_en(day_num, topic_slug, title)

    results = {}
    for lang in target_languages:
        if lang == 'en':
            insta_text = insta_en
            tele_text = tele_en
            yt_text = yt_en
        else:
            insta_text = engine.translate(insta_en, lang)
            tele_text = engine.translate(tele_en, lang)
            yt_text = engine.translate(yt_en, lang)

        hashtags = engine.get_hashtags(lang)
        insta_text = f"{insta_text}\n\n{hashtags}"

        day_dir = Path(__file__).parent / 'education' / f'day_{day_num:02d}_{topic_slug}'
        day_dir.mkdir(parents=True, exist_ok=True)

        (day_dir / f'instagram_{lang}.txt').write_text(insta_text, encoding='utf-8')
        (day_dir / f'telegram_{lang}.txt').write_text(tele_text, encoding='utf-8')
        (day_dir / f'youtube_short_{lang}.txt').write_text(yt_text, encoding='utf-8')

        results[lang] = {'instagram': len(insta_text), 'telegram': len(tele_text), 'youtube': len(yt_text)}

    return results


def generate_all_days(target_languages=None):
    """Generate all 30 days."""
    results = {}
    for day_num, _, _ in DAYS:
        log.info(f"Generating day {day_num}...")
        results[day_num] = generate_day(day_num, target_languages)
    return results


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    if '--day' in sys.argv:
        idx = sys.argv.index('--day')
        day = int(sys.argv[idx + 1])
        result = generate_day(day)
        print(f"Day {day}: {len(result)} languages generated")
        print(f"Files per language: 3 (instagram + telegram + youtube)")

    elif '--all' in sys.argv:
        result = generate_all_days()
        total_files = sum(len(r) * 3 for r in result.values())
        print(f"All 30 days generated: {total_files} files")

    elif '--test' in sys.argv:
        result = generate_day(1, ['en', 'hi', 'te', 'ar'])
        print(f"Test day 1: {len(result)} languages")
        for lang, files in result.items():
            flag = LANGUAGES.get(lang, {}).get('flag', '')
            print(f"  {flag} {lang}: {sum(files.values())} chars")

    elif '--list' in sys.argv:
        print("30-Day Education Series — Available Days:\n")
        for day_num, topic_slug, title in DAYS:
            print(f"  Day {day_num:02d}: {title} ({topic_slug})")
        print(f"\nTotal: {len(DAYS)} days")

    else:
        print("Usage:")
        print("  python education_series.py --day <N>     # Generate a specific day")
        print("  python education_series.py --all         # Generate all 30 days")
        print("  python education_series.py --test        # Test with 4 languages")
        print("  python education_series.py --list        # List all available days")
