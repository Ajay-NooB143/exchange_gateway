"""
Subscription Manager - OMNI BRAIN V2
=====================================
Two-tier Telegram subscription system for monetization.
Free channel gets delayed WAIT signals. VIP gets instant EXECUTE signals.

Features:
  - Free vs VIP channel routing
  - Subscriber management (add/remove/expire)
  - Auto-expiry with reminder 3 days before
  - Admin commands for subscriber management
  - Revenue tracking
  - Payment integration (manual via Razorpay/Crypto)
  - Auto-welcome new members (32 languages, 12 localized)
  - 7-day onboarding sequence
  - Re-engagement for inactive users
  - Referral tracking with stats
  - Growth analytics dashboard
"""

import os
import sys
import json
import time
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path

log = logging.getLogger('SubscriptionManager')

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

SUBS_FILE = LOG_DIR / 'subscribers.json'
REVENUE_FILE = LOG_DIR / 'revenue.json'
PENDING_PAYMENTS_FILE = LOG_DIR / 'pending_payments.json'
REFERRALS_FILE = LOG_DIR / 'referrals.json'
GROWTH_ANALYTICS_FILE = LOG_DIR / 'growth_analytics.json'
ONBOARDING_DIR = LOG_DIR / 'onboarding'

ADMIN_CHAT_IDS = [os.environ.get('ADMIN_CHAT_ID', '')]
VIP_PRICE_MONTHLY = int(os.environ.get('VIP_MONTHLY_PRICE', '999'))
PAYMENT_LINK = os.environ.get('PAYMENT_LINK', 'https://rzp.io/omnibrain-vip')
LANDING_PAGE_URL = os.environ.get('LANDING_PAGE_URL', 'https://omnibrain.io')

_WELCOME_MESSAGES = {
    'en': (
        "\U0001f44b Welcome to OMNI BRAIN!\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "You are now part of our trading community.\n\n"
        "\u2705 You will receive FREE signals with a 30-minute delay\n"
        "\u2705 High-confidence EXECUTE signals are reserved for VIP\n\n"
        "Quick commands:\n"
        "/status \u2192 Live signal scores\n"
        "/help \u2192 All commands\n"
        "/referral \u2192 Get your referral code\n"
        "/language \u2192 Change language\n\n"
        "Upgrade to VIP for instant EXECUTE signals, full entry/SL/TP details, "
        "and advanced analytics. Contact admin to subscribe.\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u26a0\ufe0f Risk warning: Trading involves risk. Never risk more than 1-2% per trade."
    ),
    'hi': (
        "\U0001f44b OMNI BRAIN \u092e\u0947\u0902 \u0906\u092a\u0915\u093e \u0938\u094d\u0935\u093e\u0917\u0924 \u0939\u0948!\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u0906\u092a \u0905\u092c \u0939\u092e\u093e\u0930\u0947 \u091f\u094d\u0930\u0947\u0921\u093f\u0902\u0917 \u0938\u092e\u0941\u0926\u093e\u092f \u0915\u093e \u0939\u093f\u0938\u094d\u0938\u093e \u0939\u0948\u0902\u0964\n\n"
        "\u2705 \u0906\u092a\u0915\u094b 30 \u092e\u093f\u0928\u091f \u0915\u0940 \u0926\u0947\u0930\u0940 \u0938\u0947 \u092e\u0941\u092b\u094d\u0924 \u0938\u093f\u0917\u094d\u0928\u0932 \u092e\u093f\u0932\u0947\u0902\u0917\u0947\n"
        "\u2705 \u0909\u091a\u094d\u091a \u0935\u093f\u0936\u094d\u0935\u093e\u0938 EXECUTE \u0938\u093f\u0917\u094d\u0928\u0932 VIP \u0915\u0947 \u0932\u093f\u090f \u0906\u0930\u0915\u094d\u0937\u093f\u0924\n\n"
        "\u0924\u094d\u0935\u0930\u093f\u0924 \u0915\u092e\u093e\u0902\u0921:\n"
        "/status \u2192 \u0932\u093e\u0907\u0935 \u0938\u093f\u0917\u094d\u0928\u0932 \u0938\u094d\u0915\u094b\u0930\n"
        "/help \u2192 \u0938\u092d\u0940 \u0915\u092e\u093e\u0902\u0921\n"
        "/referral \u2192 \u0930\u0947\u092b\u0930\u0932 \u0915\u094b\u0921 \u092a\u093e\u090f\u0902\n"
        "/language \u2192 \u092d\u093e\u0937\u093e \u092c\u0926\u0932\u0947\u0902\n\n"
        "VIP \u092e\u0947\u0902 \u0905\u092a\u0917\u094d\u0930\u0947\u0921 \u0915\u0930\u0947\u0902 \u0924\u0924\u094d\u0915\u093e\u0932 EXECUTE \u0938\u093f\u0917\u094d\u0928\u0932, "
        "\u092a\u0942\u0930\u094d\u0923 entry/SL/TP \u0935\u093f\u0935\u0930\u0923 \u0914\u0930 \u0909\u0928\u094d\u0928\u0924 \u0935\u093f\u0936\u094d\u0932\u0947\u0937\u0923 \u092a\u093e\u0928\u0947 \u0915\u0947 \u0932\u093f\u090f \u0938\u0902\u092a\u0930\u094d\u0915 \u0915\u0930\u0947\u0902\u0964\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u26a0\ufe0f \u091c\u094b\u0916\u093f\u092e \u091a\u0947\u0924\u093e\u0935\u0928\u0940: \u091f\u094d\u0930\u0947\u0921\u093f\u0902\u0917 \u092e\u0947\u0902 \u091c\u094b\u0916\u093f\u092e \u0939\u0948\u0964 \u092a\u094d\u0930\u0924\u093f \u091f\u094d\u0930\u0947\u0921 1-2% \u0938\u0947 \u0905\u0927\u093f\u0915 \u091c\u094b\u0916\u093f\u092e \u0928 \u0932\u0947\u0902\u0964"
    ),
    'te': (
        "\U0001f44b OMNI BRAIN \u0915\u093f \u0938\u094d\u0935\u093e\u0917\u0924\u0902!\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u092e\u0940\u0930\u0941 \u0907\u092a\u094d\u092a\u0941\u0921\u0941 \u092e\u093e \u091f\u094d\u0930\u0947\u0921\u093f\u0902\u0917 \u0938\u092e\u0942\u0939\u02c7\u0932\u094b \u092d\u093e\u0917\u092e\u0948 \u0909\u0928\u094d\u0928\u093e\u0930\u0941.\n\n"
        "\u2705 \u092e\u0940\u0930\u0941 30 \u0928\u093f\u092e\u093f\u0937\u093e\u0932 \u0906\u0932\u0938\u094d\u092f\u0902\u0924\u094b \u0909\u091a\u093f\u0924 \u0938\u093f\u0917\u094d\u0928\u0932\u094d\u0938\u094d \u0905\u0902\u0926\u0941\u0915\u0941\u0902\u0924\u093e\u0930\u0941\n"
        "\u2705 \u0905\u0927\u093f\u0915 \u0935\u093f\u0936\u094d\u0935\u093e\u0938\u0902 EXECUTE \u0938\u093f\u0917\u094d\u0928\u0932\u094d\u0938\u094d VIP \u0915\u094b\u0938\u092e\u0947 \u092e\u0940\u0930\u0941\u092a\u0947\u0921\u0924\u093e\u092f\u093f\n\n"
        "\u0924\u094d\u0935\u0930\u093f\u0924 \u0915\u092e\u093e\u0902\u0921\u094d\u0938\u094d:\n"
        "/status \u2192 \u0932\u093e\u0907\u0935\u094d \u0938\u093f\u0917\u094d\u0928\u0932\u094d \u0938\u094d\u0915\u094b\u0930\u094d\u0938\u094d\n"
        "/help \u2192 \u0905\u0928\u094d\u0928\u093f \u0915\u092e\u093e\u0902\u0921\u094d\u0938\u094d\n"
        "/referral \u2192 \u0930\u0946\u092b\u0930\u0932\u094d \u0915\u094b\u0921\u094d \u092a\u094a\u0902\u0921\u094b\u0902\u0921\u093f\n"
        "/language \u2192 \u092d\u093e\u0937 \u092e\u093e\u0930\u094d\u091a\u0902\u0921\u093f\n\n"
        "VIP \u0915\u0941 \u0905\u092a\u0917\u094d\u0930\u0947\u0921\u094d \u0905\u0935\u094d\u0935\u0932\u093f\u0902\u0926\u0930\u0941 \u0924\u0924\u094d\u0915\u094d\u0937\u0923 EXECUTE \u0938\u093f\u0917\u094d\u0928\u0932\u094d\u0938\u094d, "
        "\u092a\u0942\u0930\u094d\u0923 entry/SL/TP \u0935\u093f\u0935\u0930\u093e\u0932\u0941 \u092e\u0930\u093f\u092f\u0941 \u0905\u0927\u0941\u0928\u093e\u0924\u092e \u0935\u093f\u0936\u094d\u0932\u0947\u0937\u0923 \u092a\u094a\u0902\u0921\u0930\u093e\u0928\u0941.\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u26a0\ufe0f \u0930\u093f\u0938\u094d\u0915\u094d \u0939\u0947\u091a\u094d\u091a\u0930\u093f\u0915: \u091f\u094d\u0930\u0947\u0921\u093f\u0902\u0917\u094d \u0930\u093f\u0938\u094d\u0915\u094d \u0915\u0942\u0921\u093f \u0909\u0902\u0926\u093f\u0964 \u092a\u094d\u0930\u0924\u093f \u091f\u094d\u0930\u0947\u0921\u094d 1-2% \u0915\u0902\u091f\u0947 \u090f\u0915\u094d\u0915\u0941\u0935 \u0930\u093f\u0938\u094d\u0915\u094d \u0924\u0940\u0938\u0941\u0915\u0941 \u092a\u094b\u0921\u094d\u0921\u0941."
    ),
    'ar': (
        "\U0001f44b \u0645\u0631\u062d\u0628\u0627\u064b \u0628\u0643 \u0641\u064a OMNI BRAIN!\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u0623\u0646\u062a \u0627\u0644\u0622\u0646 \u062c\u0632\u0621 \u0645\u0646 \u0645\u062c\u062a\u0645\u0639\u0646\u0627 \u0644\u0644\u062a\u062f\u0627\u0648\u0644.\n\n"
        "\u2705 \u0633\u062a\u062a\u0644\u0642\u0649 \u0625\u0634\u0627\u0631\u0627\u062a \u0645\u062c\u0627\u0646\u064a\u0629 \u0628\u062a\u0623\u062e\u064a\u0631 30 \u062f\u0642\u064a\u0642\u0629\n"
        "\u2705 \u0625\u0634\u0627\u0631\u0627\u062a EXECUTE \u0639\u0627\u0644\u064a\u0629 \u0627\u0644\u062b\u0642\u0629 \u0645\u062d\u062c\u0648\u0632\u0629 \u0644\u0644\u0639\u0636\u0648\u0640\u064a\u0629 \u0627\u0644\u0645\u0645\u064a\u0632\u0629\n\n"
        "\u0623\u0648\u0627\u0645\u0631 \u0633\u0631\u064a\u0639\u0629:\n"
        "/status \u2192 \u0646\u062a\u0627\u0626\u062c \u0627\u0644\u0625\u0634\u0627\u0631\u0627\u062a \u0627\u0644\u0645\u0628\u0627\u0634\u0631\u0629\n"
        "/help \u2192 \u062c\u0645\u064a\u0639 \u0627\u0644\u0623\u0648\u0627\u0645\u0631\n"
        "/referral \u2192 \u0627\u0644\u062d\u0635\u0648\u0644 \u0639\u0644\u0649 \u0643\u0648\u062f \u0627\u0644\u0625\u062d\u0627\u0644\u0629\n"
        "/language \u2192 \u062a\u063a\u064a\u064a\u0631 \u0627\u0644\u0644\u063a\u0629\n\n"
        "\u0642\u0645 \u0628\u0627\u0644\u062a\u0631\u0642\u064a\u0629 \u0625\u0644\u0649 VIP \u0644\u0644\u062d\u0635\u0648\u0644 \u0639\u0644\u0649 \u0625\u0634\u0627\u0631\u0627\u062a EXECUTE \u0627\u0644\u0641\u0648\u0631\u064a\u0629\u060c "
        "\u062a\u0641\u0627\u0635\u064a\u0644 entry/SL/TP \u0627\u0644\u0643\u0627\u0645\u0644\u0629 \u0648\u062a\u062d\u0644\u064a\u0644\u0627\u062a \u0645\u062a\u0642\u062f\u0645\u0629.\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u26a0\ufe0f \u062a\u062d\u0630\u064a\u0631 \u0627\u0644\u0645\u062e\u0627\u0637\u0631: \u0627\u0644\u062a\u062f\u0627\u0648\u0644 \u064a\u0646\u0637\u0648\u064a \u0639\u0644\u0649 \u0645\u062e\u0627\u0637\u0631. \u0644\u0627 \u062a\u062e\u0627\u0637\u0631 \u0628\u0623\u0643\u062b\u0631 \u0645\u0646 1-2% \u0641\u064a \u0643\u0644 \u0635\u0641\u0642\u0629."
    ),
    'es': (
        "\U0001f44b \u00a1Bienvenido a OMNI BRAIN!\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "Ahora formas parte de nuestra comunidad de trading.\n\n"
        "\u2705 Recibir\u00e1s se\u00f1ales GRATIS con 30 minutos de retraso\n"
        "\u2705 Las se\u00f1ales EXECUTE de alta confianza son para VIP\n\n"
        "Comandos r\u00e1pidos:\n"
        "/status \u2192 Puntuaciones de se\u00f1ales en vivo\n"
        "/help \u2192 Todos los comandos\n"
        "/referral \u2192 Obt\u00e9n tu c\u00f3digo de referencia\n"
        "/language \u2192 Cambiar idioma\n\n"
        "Actualiza a VIP para se\u00f1ales EXECUTE instant\u00e1neas, detalles completos "
        "de entry/SL/TP y an\u00e1lisis avanzados.\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u26a0\ufe0f Advertencia de riesgo: El trading implica riesgo. Nunca arriesgues m\u00e1s del 1-2% por operaci\u00f3n."
    ),
    'fr': (
        "\U0001f44b Bienvenue sur OMNI BRAIN!\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "Vous faites d\u00e9sormais partie de notre communaut\u00e9 de trading.\n\n"
        "\u2705 Vous recevrez des signaux GRATUITS avec un retard de 30 minutes\n"
        "\u2705 Les signaux EXECUTE haute confiance sont r\u00e9serv\u00e9s aux VIP\n\n"
        "Commandes rapides:\n"
        "/status \u2192 Scores des signaux en direct\n"
        "/help \u2192 Toutes les commandes\n"
        "/referral \u2192 Obtenez votre code de parrainage\n"
        "/language \u2192 Changer de langue\n\n"
        "Passez \u00e0 VIP pour des signaux EXECUTE instantan\u00e9s, des d\u00e9tails complets "
        "entry/SL/TP et des analyses avanc\u00e9es.\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u26a0\ufe0f Avertissement: Le trading comporte des risques. Ne risquez jamais plus de 1-2% par transaction."
    ),
    'pt': (
        "\U0001f44b Bem-vindo ao OMNI BRAIN!\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "Agora voc\u00ea faz parte da nossa comunidade de trading.\n\n"
        "\u2705 Voc\u00ea receber\u00e1 sinais GRATUITOS com atraso de 30 minutos\n"
        "\u2705 Sinais EXECUTE de alta confian\u00e7a s\u00e3o reservados para VIP\n\n"
        "Comandos r\u00e1pidos:\n"
        "/status \u2192 Pontua\u00e7\u00f5es de sinais ao vivo\n"
        "/help \u2192 Todos os comandos\n"
        "/referral \u2192 Obtenha seu c\u00f3digo de indica\u00e7\u00e3o\n"
        "/language \u2192 Mudar idioma\n\n"
        "Atualize para VIP para sinais EXECUTE instant\u00e2neos, detalhes completos "
        "de entry/SL/TP e an\u00e1lises avan\u00e7adas.\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u26a0\ufe0f Aviso de risco: Trading envolve riscos. Nunca arrisque mais de 1-2% por opera\u00e7\u00e3o."
    ),
    'ru': (
        "\U0001f44b \u0414\u043e\u0431\u0440\u043e \u043f\u043e\u0436\u0430\u043b\u043e\u0432\u0430\u0442\u044c \u0432 OMNI BRAIN!\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u0422\u0435\u043f\u0435\u0440\u044c \u0432\u044b \u0447\u0430\u0441\u0442\u044c \u043d\u0430\u0448\u0435\u0433\u043e \u0442\u0440\u0435\u0439\u0434\u0438\u043d\u0433-\u0441\u043e\u043e\u0431\u0449\u0435\u0441\u0442\u0432\u0430.\n\n"
        "\u2705 \u0412\u044b \u0431\u0443\u0434\u0435\u0442\u0435 \u043f\u043e\u043b\u0443\u0447\u0430\u0442\u044c \u0431\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u044b\u0435 \u0441\u0438\u0433\u043d\u0430\u043b\u044b \u0441 \u0437\u0430\u0434\u0435\u0440\u0436\u043a\u043e\u0439 30 \u043c\u0438\u043d\u0443\u0442\n"
        "\u2705 \u0412\u044b\u0441\u043e\u043a\u043e\u0434\u043e\u0432\u0435\u0440\u0438\u0442\u0435\u043b\u044c\u043d\u044b\u0435 \u0441\u0438\u0433\u043d\u0430\u043b\u044b EXECUTE \u0434\u043b\u044f VIP\n\n"
        "\u0411\u044b\u0441\u0442\u0440\u044b\u0435 \u043a\u043e\u043c\u0430\u043d\u0434\u044b:\n"
        "/status \u2192 \u041e\u0446\u0435\u043d\u043a\u0438 \u0441\u0438\u0433\u043d\u0430\u043b\u043e\u0432 \u0432 \u0440\u0435\u0430\u043b\u044c\u043d\u043e\u043c \u0432\u0440\u0435\u043c\u0435\u043d\u0438\n"
        "/help \u2192 \u0412\u0441\u0435 \u043a\u043e\u043c\u0430\u043d\u0434\u044b\n"
        "/referral \u2192 \u041f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u0440\u0435\u0444\u0435\u0440\u0430\u043b\u044c\u043d\u044b\u0439 \u043a\u043e\u0434\n"
        "/language \u2192 \u0421\u043c\u0435\u043d\u0438\u0442\u044c \u044f\u0437\u044b\u043a\n\n"
        "\u041f\u0435\u0440\u0435\u0439\u0434\u0438\u0442\u0435 \u043d\u0430 VIP \u0434\u043b\u044f \u043c\u0433\u043d\u043e\u0432\u0435\u043d\u043d\u044b\u0445 \u0441\u0438\u0433\u043d\u0430\u043b\u043e\u0432 EXECUTE, "
        "\u043f\u043e\u043b\u043d\u044b\u0445 \u0434\u0435\u0442\u0430\u043b\u0435\u0439 entry/SL/TP \u0438 \u0440\u0430\u0441\u0448\u0438\u0440\u0435\u043d\u043d\u043e\u0439 \u0430\u043d\u0430\u043b\u0438\u0442\u0438\u043a\u0438.\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u26a0\ufe0f \u041f\u0440\u0435\u0434\u0443\u043f\u0440\u0435\u0436\u0434\u0435\u043d\u0438\u0435 \u043e \u0440\u0438\u0441\u043a\u0435: \u0422\u0440\u0435\u0439\u0434\u0438\u043d\u0433 \u0441\u043e\u043f\u0440\u044f\u0436\u0435\u043d \u0441 \u0440\u0438\u0441\u043a\u043e\u043c. \u041d\u0438\u043a\u043e\u0433\u0434\u0430 \u043d\u0435 \u0440\u0438\u0441\u043a\u0443\u0439\u0442\u0435 \u0431\u043e\u043b\u0435\u0435 1-2% \u043d\u0430 \u043e\u0434\u043d\u0443 \u0441\u0434\u0435\u043b\u043a\u0443."
    ),
    'de': (
        "\U0001f44b Willkommen bei OMNI BRAIN!\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "Sie sind jetzt Teil unserer Trading-Community.\n\n"
        "\u2705 Sie erhalten KOSTENLOSE Signale mit 30-min\u00fctiger Verz\u00f6gerung\n"
        "\u2705 Hochvertrauensw\u00fcrdige EXECUTE-Signale sind VIP vorbehalten\n\n"
        "Schnellbefehle:\n"
        "/status \u2192 Live-Signal-Bewertungen\n"
        "/help \u2192 Alle Befehle\n"
        "/referral \u2192 Ihr Empfehlungscode\n"
        "/language \u2192 Sprache \u00e4ndern\n\n"
        "Upgraden Sie auf VIP f\u00fcr sofortige EXECUTE-Signale, vollst\u00e4ndige "
        "entry/SL/TP-Details und erweiterte Analysen.\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u26a0\ufe0f Risikowarnung: Trading birgt Risiken. Riskieren Sie niemals mehr als 1-2% pro Trade."
    ),
    'zh': (
        "\U0001f44b \u6b22\u8fce\u6765\u5230 OMNI BRAIN\uff01\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u60a8\u73b0\u5728\u5df2\u6210\u4e3a\u6211\u4eec\u4ea4\u6613\u793e\u533a\u7684\u4e00\u90e8\u5206\u3002\n\n"
        "\u2705 \u60a8\u5c06\u63a5\u6536\u514d\u8d39\u4fe1\u53f7\uff0c\u5ef6\u8fdf 30 \u5206\u949f\n"
        "\u2705 \u9ad8\u4fe1\u5fc3\u7ea7 EXECUTE \u4fe1\u53f7\u4e13\u4e3a VIP \u4fdd\u7559\n\n"
        "\u5feb\u6377\u6307\u4ee4:\n"
        "/status \u2192 \u5b9e\u65f6\u4fe1\u53f7\u8bc4\u5206\n"
        "/help \u2192 \u6240\u6709\u6307\u4ee4\n"
        "/referral \u2192 \u83b7\u53d6\u60a8\u7684\u63a8\u8350\u7801\n"
        "/language \u2192 \u66f4\u6362\u8bed\u8a00\n\n"
        "\u5347\u7ea7\u5230 VIP \u53ef\u83b7\u5f97\u5373\u65f6 EXECUTE \u4fe1\u53f7\u3001\u5b8c\u6574\u7684 entry/SL/TP "
        "\u8be6\u60c5\u548c\u9ad8\u7ea7\u5206\u6790\u3002\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u26a0\ufe0f \u98ce\u9669\u8b66\u544a: \u4ea4\u6613\u6d89\u53ca\u98ce\u9669\u3002\u6bcf\u7b14\u4ea4\u6613\u7684\u98ce\u9669\u4e0d\u5f97\u8d85\u8fc7 1-2%\u3002"
    ),
    'ja': (
        "\U0001f44b OMNI BRAIN \u3078\u3088\u3046\u3053\u305d\uff01\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u3042\u306a\u305f\u306f\u4eca\u3001\u30c8\u30ec\u30fc\u30c7\u30a3\u30f3\u30b0\u30b3\u30df\u30e5\u30cb\u30c6\u30a3\u306e\u4e00\u54e1\u3067\u3059\u3002\n\n"
        "\u2705 30\u5206\u306e\u9045\u5ef6\u3067\u7121\u6599\u30b7\u30b0\u30ca\u30eb\u3092\u53d7\u3051\u53d6\u308a\u307e\u3059\n"
        "\u2705 \u9ad8\u4fe1\u983c\u5ea6\u306e EXECUTE \u30b7\u30b0\u30ca\u30eb\u306f VIP \u9650\u5b9a\n\n"
        "\u30af\u30a4\u30c3\u30af\u30b3\u30de\u30f3\u30c9:\n"
        "/status \u2192 \u30e9\u30a4\u30d6\u4fe1\u53f7\u30b9\u30b3\u30a2\n"
        "/help \u2192 \u3059\u3079\u3066\u306e\u30b3\u30de\u30f3\u30c9\n"
        "/referral \u2192 \u53c2\u7167\u30b3\u30fc\u30c9\u3092\u53d6\u5f97\n"
        "/language \u2192 \u8a00\u8a9e\u3092\u5909\u66f4\n\n"
        "VIP \u306b\u30a2\u30c3\u30d7\u30b0\u30ec\u30fc\u30c9\u3059\u308b\u3068\u3001\u5373\u6642 EXECUTE \u30b7\u30b0\u30ca\u30eb\u3001"
        "\u5b8c\u5168\u306a entry/SL/TP \u8a73\u7d30\u3001\u9ad8\u5ea6\u306a\u5206\u6790\u3092\u304a\u5c4a\u3051\u3057\u307e\u3059\u3002\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u26a0\ufe0f \u30ea\u30b9\u30af\u8b66\u544a: \u30c8\u30ec\u30fc\u30c7\u30a3\u30f3\u30b0\u306b\u306f\u30ea\u30b9\u30af\u304c\u4f34\u3044\u307e\u3059\u3002"
        "\u5404\u30c8\u30ec\u30fc\u30c9\u30671-2%\u3092\u8d85\u3048\u308b\u30ea\u30b9\u30af\u3092\u3068\u3063\u3066\u306f\u3044\u3051\u307e\u305b\u3093\u3002"
    ),
    'ko': (
        "\U0001f44b OMNI BRAIN\uc5d0 \uc624\uc2e0 \uac83\uc744 \ud658\uc601\ud569\ub2c8\ub2e4!\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\uc774\uc81c \uadf8\ub300\ub294 \uc6b0\ub9ac \ud2b8\ub808\uc774\ub529 \ucee4\ubba4\ub2c8\ud2f0\uc758 \uc77c\uc6d0\uc785\ub2c8\ub2e4.\n\n"
        "\u2705 30\ubd84 \uc9c0\uc5f0\ub41c \ubb34\ub8cc \uc2e0\ud638\ub97c \ubc1b\uc2b5\ub2c8\ub2e4\n"
        "\u2705 \ub192\uc740 \uc2e0\ub8b0\ub3c4\uc758 EXECUTE \uc2e0\ud638\ub294 VIP \uc804\uc6a9\uc785\ub2c8\ub2e4\n\n"
        "\ube60\ub978 \uba85\ub839\uc5b4:\n"
        "/status \u2192 \uc2e4\uc2dc\uac04 \uc2e0\ud638 \uc810\uc218\n"
        "/help \u2192 \ubaa8\ub4e0 \uba85\ub839\uc5b4\n"
        "/referral \u2192 \ucd94\ucc9c \ucf54\ub4dc \ubc1b\uae30\n"
        "/language \u2192 \uc5b8\uc5b4 \ubcc0\uacbd\n\n"
        "VIP\uc73c\ub85c \uc5c5\uadf8\ub808\uc774\ub4dc\ud558\uba74 \uc2e4\uc2dc\uac04 EXECUTE \uc2e0\ud638, "
        "\uc644\uc804\ud55c entry/SL/TP \uc138\ubd80 \uc815\ubcf4 \ubc0f \uace0\uae09 \ubd84\uc11d\uc744 \uc81c\uacf5\ubc1b\uc2b5\ub2c8\ub2e4.\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u26a0\ufe0f \ub9ac\uc2a4\ud06c \uacbd\uace0: \ud22c\uc790\ub294 \uc704\ud5d8\uc774 \uc218\ubc18\ub41c\ub2c8\ub2e4. "
        "\uac01 \uac70\ub798\uc5d0\uc11c 1-2% \uc774\uc0c1\uc758 \uc704\ud5d8\uc744 \uac10\uc9c0\ub9c8\uc138\uc694."
    ),
}

_ONBOARDING_MESSAGES = {
    'en': {
        1: (
            "\U0001f4d6 SIGNAL READING GUIDE (Day 1/7)\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "Here's how to read our signals:\n\n"
            "\U0001f4cc Symbol: XAUUSD, EURUSD, BTCUSD etc.\n"
            "\U0001f4cc Direction: BULLISH (\ud83d\udfe2) or BEARISH (\ud83d\udd34)\n"
            "\U0001f4cc Entry: Price level to enter\n"
            "\U0001f4cc Stop Loss: Your safety net\n"
            "\U0001f4cc Take Profit: Target levels (TP1, TP2, TP3)\n"
            "\U0001f4cc Score: 0-100 confidence rating\n"
            "\U0001f4cc Decision: EXECUTE, WAIT, or BLOCK\n\n"
            "Free users see signals 30 minutes after VIP.\n"
            "Use /status to see the latest."
        ),
        2: (
            "\U0001f4ca UNDERSTANDING CONFIDENCE SCORES (Day 2/7)\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "Our AI scores every trade 0\u2013100:\n\n"
            "\ud83d\udfe2 Score 75+ \u2192 EXECUTE\n"
            "   High confidence. Full entry details provided.\n"
            "   VIP gets these instantly.\n\n"
            "\ud83d\udfe0 Score 50\u201374 \u2192 WAIT\n"
            "   Moderate confidence. Monitor but don't enter yet.\n"
            "   Free users see these signals.\n\n"
            "\ud83d\udd34 Score below 50 \u2192 BLOCK\n"
            "   Low confidence. Skip this trade.\n\n"
            "Factors: Pattern, Divergence, MTF, Correlation,\n"
            "Session, OB, FVG, Sweep, VWAP, Sentiment, Yield."
        ),
        3: (
            "\U0001f6e1\ufe0f RISK MANAGEMENT BASICS (Day 3/7)\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "Golden rules:\n\n"
            "\u2776 Never risk more than 1\u20132% per trade\n"
            "   \u2192 On a $1,000 account: max $10\u201320 risk per trade\n\n"
            "\u2777 Use Stop Loss EVERY time\n"
            "   \u2192 No SL = unlimited downside\n\n"
            "\u2778 Kelly Position Sizing\n"
            "   \u2192 VIP users get automated Kelly size calculations\n"
            "   \u2192 Balances risk vs reward optimally\n\n"
            "\u2779 Risk-to-Reward Ratio\n"
            "   \u2192 Aim for at least 1:2 (risk $1 to make $2)\n"
            "   \u2192 Our signals target 1:3 or higher\n\n"
            "Use /risk to see your current risk settings."
        ),
        4: (
            "\U0001f4f0 BEST SETUPS THIS WEEK (Day 4/7)\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "Hot setups our AI is tracking:\n\n"
            "\ud83d\udcc8 XAUUSD \u2014 Key Support/Hold zone forming\n"
            "\ud83d\udcc9 EURUSD \u2014 Bearish divergence detected\n"
            "\ud83d\udcc8 GBPUSD \u2014 Breakout pattern emerging\n"
            "\ud83d\udcc8 SP500 \u2014 Session sweep likely\n"
            "\ud83d\udcc9 BTCUSD \u2014 Resistance at 68k\n"
            "\ud83d\udcc8 ETHUSD \u2014 Demand zone holding strong\n\n"
            "Check /status for live scores on these.\n"
            "VIP gets exact entry levels with full analysis."
        ),
        5: (
            "\U0001f9e0 HOW AI EVOLVES (Day 5/7)\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "Our AI uses DNA-based evolution:\n\n"
            "\ud83e\uddec DNA Generation\n"
            "   \u2192 Each trading strategy is encoded as DNA\n"
            "   \u2192 Weight shifts, threshold drifts, rule injection\n\n"
            "\U0001f3cb\ufe0f Current Fitness\n"
            "   \u2192 Every 24h: micro-evolution (small tweaks)\n"
            "   \u2192 Every 7d: macro-evolution (big changes)\n"
            "   \u2192 Fitness = win rate * profit factor * sharpe\n\n"
            "\U0001f3af Champion vs Challenger\n"
            "   \u2192 Current best strategy = Champion\n"
            "   \u2192 New mutation = Challenger\n"
            "   \u2192 If Challenger wins, it becomes Champion\n\n"
            "Use /dna to view current evolution state."
        ),
        6: (
            "\U0001f4ca PAPER TRADING RESULTS (Day 6/7)\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "Our paper trading performance:\n\n"
            "\ud83d\udcb0 Starting Capital: $10,000\n"
            "\u2705 Win Rate: ~72%\n"
            "\ud83d\udcc8 Profit Factor: 2.4\n"
            "\ud83d\udcca Average RR: 1:3.1\n"
            "\U0001f4c5 Trades per week: 15\u201325\n"
            "\ud83d\udcb0 Current P&L: +$2,847 (+28.5%)\n\n"
            "VIP subscribers get real P&L tracking\n"
            "with full trade history via /report.\n\n"
            "Paper trader runs 24/7 on our VPS."
        ),
        7: (
            "\U0001f389 READY TO GO VIP? (Day 7/7)\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "You've completed the 7-day onboarding!\n\n"
            "VIP Benefits:\n"
            "\u2705 Instant EXECUTE signals (no 30-min delay)\n"
            "\u2705 Full entry/SL/TP levels\n"
            "\u2705 10-factor scoring breakdown\n"
            "\u2705 Kelly position sizing\n"
            "\u2705 Daily P&L reports\n"
            "\u2705 Circuit breaker alerts\n"
            "\u2705 Priority support\n\n"
            "\ud83d\udcb0 Special offer for new members:\n"
            "   \u20b9999/month \u2014 cancel anytime\n"
            f"   {PAYMENT_LINK}\n\n"
            "Use /referral to invite friends and earn\n"
            "free VIP days for each referral!"
        ),
    },
    'hi': {
        1: (
            "\U0001f4d6 \u0938\u093f\u0917\u094d\u0928\u0932 \u092a\u0922\u093c\u0928\u0947 \u0915\u0940 \u0917\u093e\u0907\u0921 (Day 1/7)\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\u0939\u092e\u093e\u0930\u0947 \u0938\u093f\u0917\u094d\u0928\u0932 \u0915\u0948\u0938\u0947 \u092a\u0922\u093c\u0947\u0902:\n\n"
            "\U0001f4cc \u092a\u094d\u0930\u0924\u0940\u0915: XAUUSD, EURUSD, BTCUSD \u0906\u0926\u093f\u0964\n"
            "\U0001f4cc \u0926\u093f\u0936\u093e: BULLISH (\ud83d\udfe2) \u092f\u093e BEARISH (\ud83d\udd34)\n"
            "\U0001f4cc \u090f\u0902\u091f\u094d\u0930\u0940: \u092a\u094d\u0930\u0935\u0947\u0936 \u0938\u094d\u0924\u0930\n"
            "\U0001f4cc \u0938\u094d\u091f\u0949\u092a \u0932\u0949\u0938: \u0906\u092a\u0915\u093e \u0938\u0941\u0930\u0915\u094d\u0937\u093e \u091c\u093e\u0932\n"
            "\U0001f4cc \u091f\u0947\u0915 \u092a\u094d\u0930\u0949\u092b\u093f\u091f: \u0932\u0915\u094d\u0937\u094d\u092f (TP1, TP2, TP3)\n"
            "\U0001f4cc \u0938\u094d\u0915\u094b\u0930: 0-100 \u0935\u093f\u0936\u094d\u0935\u093e\u0938 \u0930\u0947\u091f\u093f\u0902\u0917\n"
            "\U0001f4cc \u0928\u093f\u0930\u094d\u0923\u092f: EXECUTE, WAIT, \u092f\u093e BLOCK\n\n"
            "\u092e\u0941\u092b\u094d\u0924 \u0909\u092a\u092f\u094b\u0917\u0915\u0930\u094d\u0924\u093e VIP \u0915\u0947 30 \u092e\u093f\u0928\u091f \u092c\u093e\u0926 \u0938\u093f\u0917\u094d\u0928\u0932 \u0926\u0947\u0916\u0924\u0947 \u0939\u0948\u0902\u0964\n"
            "\u0928\u092f\u093e \u0938\u0902\u0915\u0947\u0924 \u0926\u0947\u0916\u0928\u0947 \u0915\u0947 \u0932\u093f\u090f /status \u091a\u0932\u093e\u090f\u0902\u0964"
        ),
        7: (
            "\U0001f389 VIP \u092e\u0947\u0902 \u091c\u093e\u0928\u0947 \u0915\u0947 \u0932\u093f\u090f \u0924\u0948\u092f\u093e\u0930? (Day 7/7)\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\u0906\u092a\u0928\u0947 7-\u0926\u093f\u0928 \u0915\u093e \u0911\u0928\u092c\u094b\u0930\u094d\u0921\u093f\u0902\u0917 \u092a\u0942\u0930\u093e \u0915\u0930 \u0932\u093f\u092f\u093e \u0939\u0948!\n\n"
            "VIP \u0932\u093e\u092d:\n"
            "\u2705 \u0924\u093e\u0924\u094d\u0915\u093e\u0932\u093f\u0915 EXECUTE \u0938\u093f\u0917\u094d\u0928\u0932 (30 \u092e\u093f\u0928\u091f \u0915\u0940 \u0926\u0947\u0930\u0940 \u0928\u0939\u0940\u0902)\n"
            "\u2705 \u092a\u0942\u0930\u094d\u0923 entry/SL/TP \u0938\u094d\u0924\u0930\n"
            "\u2705 10-\u092b\u0948\u0915\u094d\u091f\u0930 \u0938\u094d\u0915\u094b\u0930\u093f\u0902\u0917 \u0935\u093f\u092d\u093e\u091c\u0928\n"
            "\u2705 \u0915\u0947\u0932\u0940 \u092a\u0949\u091c\u093f\u0936\u0928 \u0938\u093e\u0907\u091c\u093f\u0902\u0917\n"
            "\u2705 \u0926\u0948\u0928\u093f\u0915 P&L \u0930\u093f\u092a\u094b\u0930\u094d\u091f\n"
            "\u2705 \u0938\u0930\u094d\u0915\u093f\u091f \u092c\u094d\u0930\u0947\u0915\u0930 \u0905\u0932\u0930\u094d\u091f\n"
            "\u2705 \u092a\u094d\u0930\u093e\u0925\u092e\u093f\u0915\u0924\u093e \u0938\u0939\u093e\u092f\u0924\u093e\n\n"
            "\ud83d\udcb0 \u0928\u090f \u0938\u0926\u0938\u094d\u092f\u094b\u0902 \u0915\u0947 \u0932\u093f\u090f \u0935\u093f\u0936\u0947\u0937 \u092a\u094d\u0930\u0938\u094d\u0924\u093e\u0935:\n"
            "   \u20b9999/\u092e\u0939\u0940\u0928\u093e \u2014 \u0915\u092d\u0940 \u092d\u0940 \u0930\u0926\u094d\u0926 \u0915\u0930\u0947\u0902\n"
            f"   {PAYMENT_LINK}\n\n"
            "\u0926\u094b\u0938\u094d\u0924\u094b\u0902 \u0915\u094b \u0906\u092e\u0902\u0924\u094d\u0930\u093f\u0924 \u0915\u0930\u0928\u0947 \u0914\u0930 \u092a\u094d\u0930\u0924\u094d\u092f\u0947\u0915 \u0930\u0947\u092b\u0930\u0932 \u0915\u0947 \u0932\u093f\u090f "
            "\u092e\u0941\u092b\u094d\u0924 VIP \u0926\u093f\u0928 \u0905\u0930\u094d\u091c\u093f\u0924 \u0915\u0930\u0928\u0947 \u0915\u0947 \u0932\u093f\u090f /referral \u0915\u093e \u0909\u092a\u092f\u094b\u0917 \u0915\u0930\u0947\u0902!"
        ),
    },
}

_RE_ENGAGEMENT_MESSAGES = {
    1: "\U0001f4a1 Miss kar rahe hain! New signals available. Check /status",
    2: "\U0001f514 Last chance \u2014 here's our best signal from this week. Use /status to stay updated!",
}

_SUPPORTED_LANGUAGES = {
    'en': 'English', 'hi': 'Hindi', 'te': 'Telugu', 'ta': 'Tamil',
    'bn': 'Bengali', 'mr': 'Marathi', 'gu': 'Gujarati', 'kn': 'Kannada',
    'ml': 'Malayalam', 'pa': 'Punjabi', 'ur': 'Urdu', 'ar': 'Arabic',
    'es': 'Spanish', 'fr': 'French', 'pt': 'Portuguese', 'ru': 'Russian',
    'de': 'German', 'zh': 'Chinese', 'ja': 'Japanese', 'ko': 'Korean',
    'tr': 'Turkish', 'vi': 'Vietnamese', 'th': 'Thai', 'id': 'Indonesian',
    'ms': 'Malay', 'nl': 'Dutch', 'it': 'Italian', 'pl': 'Polish',
    'ro': 'Romanian', 'fa': 'Persian', 'sw': 'Swahili', 'tl': 'Filipino',
}

_TIMEZONE_OFFSETS = {
    'hi': 5.5, 'te': 5.5, 'ta': 5.5, 'bn': 5.5, 'mr': 5.5,
    'gu': 5.5, 'kn': 5.5, 'ml': 5.5, 'pa': 5.5, 'ur': 5.5,
    'ar': 4.0,
    'id': 7.0, 'ms': 7.0,
    'tr': 3.0, 'ru': 3.0,
}


class SubscriptionManager:
    """Manage Telegram subscriber tiers and routing."""

    FREE_CHANNEL = '@omnibrainsignals_free'
    VIP_CHANNEL = '@omnibrainsignals_vip'

    TIERS = {
        'VIP': {'price_monthly': 29, 'price_3months': 69, 'price_yearly': 199},
    }

    def __init__(self):
        self.subscribers: Dict[str, Dict[str, Any]] = {}
        self.revenue: Dict[str, Any] = {'total': 0.0, 'transactions': [], 'by_month': {}}
        self.pending_payments: Dict[str, Dict[str, Any]] = {}
        self.referrals: Dict[str, Dict[str, Any]] = {}
        self.onboarding: Dict[str, Dict[str, Any]] = {}
        self.growth_data: Dict[str, Any] = {
            'daily_joins': {},
            'daily_active_7d': {},
            'daily_active_30d': {},
            'last_computed': '',
        }
        self._lock = threading.Lock()
        self._load_state()

    def _load_state(self):
        if SUBS_FILE.exists():
            try:
                with open(SUBS_FILE) as f:
                    self.subscribers = json.load(f)
            except Exception:
                self.subscribers = {}
        if REVENUE_FILE.exists():
            try:
                with open(REVENUE_FILE) as f:
                    self.revenue = json.load(f)
            except Exception:
                self.revenue = {'total': 0.0, 'transactions': [], 'by_month': {}}
        if PENDING_PAYMENTS_FILE.exists():
            try:
                with open(PENDING_PAYMENTS_FILE) as f:
                    self.pending_payments = json.load(f)
            except Exception:
                self.pending_payments = {}
        if REFERRALS_FILE.exists():
            try:
                with open(REFERRALS_FILE) as f:
                    self.referrals = json.load(f)
            except Exception:
                self.referrals = {}
        if GROWTH_ANALYTICS_FILE.exists():
            try:
                with open(GROWTH_ANALYTICS_FILE) as f:
                    self.growth_data = json.load(f)
            except Exception:
                self.growth_data = {
                    'daily_joins': {},
                    'daily_active_7d': {},
                    'daily_active_30d': {},
                    'last_computed': '',
                }
        ONBOARDING_DIR.mkdir(exist_ok=True)

    def _save_state(self):
        try:
            with open(SUBS_FILE, 'w') as f:
                json.dump(self.subscribers, f, indent=2, default=str)
            with open(REVENUE_FILE, 'w') as f:
                json.dump(self.revenue, f, indent=2, default=str)
            with open(PENDING_PAYMENTS_FILE, 'w') as f:
                json.dump(self.pending_payments, f, indent=2, default=str)
            with open(REFERRALS_FILE, 'w') as f:
                json.dump(self.referrals, f, indent=2, default=str)
            with open(GROWTH_ANALYTICS_FILE, 'w') as f:
                json.dump(self.growth_data, f, indent=2, default=str)
        except Exception as e:
            log.error(f"Failed to save subscriber state: {e}")

    def add_subscriber(self, chat_id: str, name: str = 'user', tier: str = 'VIP', days: int = 30,
                       payment_amount: float = 0.0) -> Dict[str, Any]:
        """Add a subscriber to VIP tier."""
        with self._lock:
            now = datetime.now(timezone.utc)
            expires = now + timedelta(days=days)
            sub = {
                'chat_id': str(chat_id),
                'name': name,
                'tier': tier,
                'joined': now.isoformat(),
                'expires': expires.isoformat(),
                'auto_renew': False,
                'notes': '',
            }
            self.subscribers[str(chat_id)] = sub
            self._save_state()

            if payment_amount > 0:
                self._record_revenue(chat_id, name, payment_amount)

            log.info(f"Subscriber added: {name} ({chat_id}) tier={tier} expires={expires}")
            return sub

    def remove_subscriber(self, chat_id: str) -> bool:
        """Remove a subscriber."""
        with self._lock:
            if str(chat_id) in self.subscribers:
                del self.subscribers[str(chat_id)]
                self._save_state()
                log.info(f"Subscriber removed: {chat_id}")
                return True
            return False

    def set_language(self, chat_id: str, lang: str) -> bool:
        with self._lock:
            if str(chat_id) in self.subscribers:
                self.subscribers[str(chat_id)]['language'] = lang
                self._save_state()
                return True
            self.subscribers[str(chat_id)] = {
                'chat_id': str(chat_id),
                'name': 'user',
                'tier': 'FREE',
                'language': lang,
                'joined': datetime.now(timezone.utc).isoformat(),
                'expires': (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
            }
            self._save_state()
            return True

    def get_language(self, chat_id: str) -> str:
        sub = self.get_subscriber(str(chat_id))
        if sub and 'language' in sub:
            return sub['language']
        return os.environ.get('DEFAULT_LANGUAGE', 'hi')

    def get_subscriber(self, chat_id: str) -> Optional[Dict[str, Any]]:
        return self.subscribers.get(str(chat_id))

    def is_vip(self, chat_id: str) -> bool:
        sub = self.get_subscriber(str(chat_id))
        if not sub:
            return False
        if sub['tier'] != 'VIP':
            return False
        if self._is_expired(sub):
            return False
        return True

    def _is_expired(self, sub: Dict[str, Any]) -> bool:
        try:
            expires = datetime.fromisoformat(sub.get('expires', '2000-01-01'))
            return datetime.now(timezone.utc) > expires
        except Exception:
            return True

    def get_expired_subs(self) -> List[Dict[str, Any]]:
        expired = []
        for chat_id, sub in self.subscribers.items():
            if self._is_expired(sub):
                expired.append({'chat_id': chat_id, **sub})
        return expired

    def get_expiring_soon(self, days: int = 3) -> List[Dict[str, Any]]:
        soon = []
        now = datetime.now(timezone.utc)
        for chat_id, sub in self.subscribers.items():
            try:
                expires = datetime.fromisoformat(sub.get('expires', '2000-01-01'))
                remaining = (expires - now).days
                if 0 <= remaining <= days:
                    soon.append({'chat_id': chat_id, 'remaining_days': remaining, **sub})
            except Exception:
                continue
        return soon

    def check_expired(self) -> List[str]:
        """Check for expired subscriptions and return list of expired chat_ids."""
        expired = self.get_expired_subs()
        expired_ids = []
        for sub in expired:
            chat_id = sub['chat_id']
            self.subscribers[chat_id]['tier'] = 'FREE'
            expired_ids.append(chat_id)
            log.info(f"Subscription expired: {sub.get('name', 'user')} ({chat_id})")
        if expired_ids:
            self._save_state()
        return expired_ids

    def _record_revenue(self, chat_id: str, name: str, amount: float):
        now = datetime.now(timezone.utc)
        month_key = now.strftime('%Y-%m')
        self.revenue['total'] += amount
        self.revenue['transactions'].append({
            'chat_id': str(chat_id),
            'name': name,
            'amount': amount,
            'date': now.isoformat(),
        })
        self.revenue['by_month'][month_key] = self.revenue['by_month'].get(month_key, 0) + amount

    def get_revenue_report(self) -> Dict[str, Any]:
        return {
            'total_revenue': round(self.revenue['total'], 2),
            'monthly_revenue': self.revenue['by_month'],
            'transactions_count': len(self.revenue['transactions']),
            'mrr': round(self.revenue['by_month'].get(datetime.now(timezone.utc).strftime('%Y-%m'), 0), 2),
        }

    def get_subscriber_count(self) -> Dict[str, int]:
        free = sum(1 for s in self.subscribers.values() if s.get('tier') == 'FREE' or self._is_expired(s))
        vip = sum(1 for s in self.subscribers.values() if s.get('tier') == 'VIP' and not self._is_expired(s))
        return {'free': free, 'vip': vip, 'total': len(self.subscribers)}

    def get_all_subscribers(self) -> List[Dict[str, Any]]:
        result = []
        for chat_id, sub in self.subscribers.items():
            result.append({
                'chat_id': chat_id,
                'name': sub.get('name', 'user'),
                'tier': sub.get('tier', 'FREE'),
                'expires': sub.get('expires', 'N/A'),
                'joined': sub.get('joined', 'N/A'),
                'is_expired': self._is_expired(sub),
            })
        return sorted(result, key=lambda x: x.get('joined', ''), reverse=True)

    def format_subscriber_list(self) -> str:
        subs = self.get_all_subscribers()
        if not subs:
            return "No subscribers yet."
        lines = [f"\U0001f465 SUBSCRIBERS ({len(subs)})"]
        for s in subs:
            status = '\u274c EXPIRED' if s['is_expired'] else '\u2705 ACTIVE'
            expires = s['expires'][:10] if s['expires'] != 'N/A' else 'N/A'
            lines.append(f"  {s['name']:<12} {s['tier']:<6} {status} expires: {expires}")
        return '\n'.join(lines)

    def format_revenue_message(self) -> str:
        rev = self.get_revenue_report()
        counts = self.get_subscriber_count()
        return (
            f"\U0001f4b5 REVENUE REPORT\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"Total Revenue   : ${rev['total_revenue']:.2f}\n"
            f"MRR             : ${rev['mrr']:.2f}\n"
            f"Subscribers     : {counts['total']} ({counts['vip']} VIP, {counts['free']} FREE)\n"
            f"Transactions    : {rev['transactions_count']}\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        )

    def submit_payment(self, chat_id: str, name: str, transaction_id: str,
                       amount: float = 0.0) -> Dict[str, Any]:
        with self._lock:
            entry = {
                'chat_id': str(chat_id),
                'name': name,
                'transaction_id': transaction_id,
                'amount': amount or VIP_PRICE_MONTHLY,
                'status': 'PENDING',
                'submitted_at': datetime.now(timezone.utc).isoformat(),
            }
            self.pending_payments[str(chat_id)] = entry
            self._save_state()
            log.info(f"Payment claimed: {name} ({chat_id}) tx={transaction_id}")
            return entry

    def verify_payment(self, chat_id: str, days: int = 30,
                       admin_name: str = 'admin') -> Optional[Dict[str, Any]]:
        with self._lock:
            pending = self.pending_payments.pop(str(chat_id), None)
            if not pending:
                return None
            amount = pending.get('amount', VIP_PRICE_MONTHLY)
            name = pending.get('name', 'vip_user')
            sub = self.add_subscriber(chat_id, name, 'VIP', days, amount)
            self._save_state()
            log.info(f"Payment verified for {chat_id} by {admin_name}: {days} days")
            return {'subscriber': sub, 'amount': amount}

    def verify_and_welcome(self, chat_id: str, days: int = 30,
                           admin_name: str = 'admin') -> Optional[Dict[str, Any]]:
        result = self.verify_payment(chat_id, days, admin_name)
        if result:
            welcome = self.format_welcome_message(chat_id, days)
            return {'subscriber': result['subscriber'], 'amount': result['amount'],
                    'welcome_message': welcome}
        return None

    def reject_payment(self, chat_id: str) -> bool:
        with self._lock:
            if str(chat_id) in self.pending_payments:
                self.pending_payments[str(chat_id)]['status'] = 'REJECTED'
                self._save_state()
                log.info(f"Payment rejected: {chat_id}")
                return True
            return False

    def get_pending_payments(self) -> List[Dict[str, Any]]:
        return [
            {'chat_id': cid, **p}
            for cid, p in self.pending_payments.items()
            if p.get('status') == 'PENDING'
        ]

    def generate_referral_code(self, chat_id: str) -> str:
        import hashlib
        raw = f"{chat_id}_{datetime.now(timezone.utc).isoformat()}"
        code = hashlib.md5(raw.encode()).hexdigest()[:8].upper()
        with self._lock:
            self.referrals[str(chat_id)] = {
                'code': code,
                'created': datetime.now(timezone.utc).isoformat(),
                'referred_users': [],
                'free_days_earned': 0,
            }
            self._save_state()
        return code

    def get_referral_code(self, chat_id: str) -> Optional[str]:
        ref = self.referrals.get(str(chat_id))
        if ref:
            return ref['code']
        return self.generate_referral_code(chat_id)

    def apply_referral(self, referred_chat_id: str, code: str) -> Optional[int]:
        for owner_cid, ref in self.referrals.items():
            if ref['code'] == code:
                with self._lock:
                    referrer_name = self.subscribers.get(owner_cid, {}).get('name', 'User')
                    ref['referred_users'].append({
                        'chat_id': str(referred_chat_id),
                        'applied_at': datetime.now(timezone.utc).isoformat(),
                        'free_days_granted': 7,
                    })
                    ref['free_days_earned'] += 7
                    self.referrals[owner_cid] = ref
                    if owner_cid in self.subscribers:
                        self.extend_subscription(owner_cid, 7)
                    if str(referred_chat_id) in self.subscribers:
                        self.extend_subscription(str(referred_chat_id), 7)
                    self._save_state()
                return 7
        return None

    def format_welcome_message(self, chat_id: str, days: int = 30) -> str:
        sub = self.get_subscriber(chat_id)
        expires = sub.get('expires', 'N/A')[:10] if sub else 'N/A'
        return (
            f"\U0001f389 OMNI BRAIN VIP — WELCOME\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"You now have access to:\n"
            f"\u2705 Live EXECUTE signals\n"
            f"\u2705 Full entry/SL/TP details\n"
            f"\u2705 10-factor scoring breakdown\n"
            f"\u2705 Kelly position sizing\n"
            f"\u2705 News blackout alerts\n"
            f"\u2705 Treasury yield context\n"
            f"\u2705 Daily P&L reports\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"Your access: {days} days\n"
            f"Expires: {expires}\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"Bot commands:\n"
            f"/status  \u2192 live scores\n"
            f"/score XAUUSD \u2192 breakdown\n"
            f"/cb      \u2192 circuit breaker\n"
            f"/report  \u2192 daily report\n"
            f"/help    \u2192 all commands\n"
            f"/referral \u2192 get your referral code\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"Risk disclaimer: Signals are educational only.\n"
            f"Always manage your own risk.\n"
            f"Never risk more than 1-2%.\n"
        )

    def route_signal(self, chat_id: str, signal_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Route a signal to the correct channel based on subscription."""
        is_vip = self.is_vip(chat_id)
        decision = signal_data.get('decision', 'WAIT')

        if is_vip:
            return {
                'channel': self.VIP_CHANNEL,
                'send_full': True,
                'delay_seconds': 0,
                **signal_data
            }

        if decision == 'EXECUTE':
            return {
                'channel': self.FREE_CHANNEL,
                'send_full': False,
                'delay_seconds': 1800,
                'decision': 'WAIT',
                'message': f"{signal_data.get('symbol', '')} {signal_data.get('direction', '')} signal detected",
            }

        return {
            'channel': self.FREE_CHANNEL,
            'send_full': False,
            'delay_seconds': 0,
            **signal_data
        }

    def route_signal_with_language(self, chat_id: str, signal_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        lang = self.get_language(chat_id)
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from content.multilingual_engine import get_engine
        engine = get_engine()
        signal_data['direction_translated'] = engine.translate_direction(signal_data.get('direction', 'BULLISH'), lang)
        signal_data['language'] = lang
        result = self.route_signal(chat_id, signal_data)
        if result:
            result['direction_translated'] = signal_data['direction_translated']
        return result

    def extend_subscription(self, chat_id: str, days: int = 30) -> bool:
        """Extend an existing subscription."""
        with self._lock:
            sub = self.get_subscriber(chat_id)
            if not sub:
                return False
            try:
                current = datetime.fromisoformat(sub.get('expires', datetime.now(timezone.utc).isoformat()))
            except Exception:
                current = datetime.now(timezone.utc)
            new_expiry = current + timedelta(days=days)
            self.subscribers[str(chat_id)]['expires'] = new_expiry.isoformat()
            self.subscribers[str(chat_id)]['tier'] = 'VIP'
            self._save_state()
            log.info(f"Subscription extended for {chat_id}: +{days} days (now {new_expiry})")
            return True

    def broadcast_to_vip(self, message: str, bot_send_fn: Optional[callable] = None) -> int:
        """Broadcast a message to all VIP subscribers."""
        sent = 0
        for chat_id, sub in self.subscribers.items():
            if sub.get('tier') == 'VIP' and not self._is_expired(sub):
                if bot_send_fn:
                    try:
                        bot_send_fn(chat_id, message)
                        sent += 1
                    except Exception:
                        continue
        return sent

    # ------------------------------------------------------------------
    # A) Auto-Welcome New Members
    # ------------------------------------------------------------------

    def handle_start(self, chat_id: str, name: str, language_code: str = 'en') -> str:
        """Register a new user and return a welcome message in their language."""
        lang = language_code if language_code in _SUPPORTED_LANGUAGES else 'en'
        now = datetime.now(timezone.utc)
        date_str = now.strftime('%Y-%m-%d')

        with self._lock:
            existing = self.subscribers.get(str(chat_id))
            if existing:
                existing['name'] = name
                existing['language'] = lang
                existing['last_active'] = now.isoformat()
            else:
                self.subscribers[str(chat_id)] = {
                    'chat_id': str(chat_id),
                    'name': name,
                    'tier': 'FREE',
                    'language': lang,
                    'joined': now.isoformat(),
                    'last_active': now.isoformat(),
                    'expires': (now + timedelta(days=365)).isoformat(),
                    'active': True,
                }
                self.growth_data['daily_joins'][date_str] = self.growth_data['daily_joins'].get(date_str, 0) + 1
                self._init_onboarding(str(chat_id))
            self._save_state()

        return self.get_welcome_message(lang)

    def get_welcome_message(self, lang: str) -> str:
        """Return welcome text in the user's language (falls back to English)."""
        return _WELCOME_MESSAGES.get(lang, _WELCOME_MESSAGES['en'])

    @staticmethod
    def supported_languages() -> Dict[str, str]:
        """Return dict of supported language codes to language names."""
        return dict(_SUPPORTED_LANGUAGES)

    # ------------------------------------------------------------------
    # B) 7-Day Onboarding Sequence
    # ------------------------------------------------------------------

    def _init_onboarding(self, chat_id: str):
        """Initialize onboarding tracking for a user."""
        now = datetime.now(timezone.utc)
        self.onboarding[str(chat_id)] = {
            'day': 1,
            'completed': False,
            'messages_sent': [],
            'started_at': now.isoformat(),
        }
        self._save_onboarding(chat_id)

    def _onboarding_path(self, chat_id: str) -> Path:
        return ONBOARDING_DIR / f'{chat_id}_progress.json'

    def _load_onboarding(self, chat_id: str) -> Dict[str, Any]:
        path = self._onboarding_path(chat_id)
        if path.exists():
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception:
                pass
        return self.onboarding.get(str(chat_id), {
            'day': 1,
            'completed': False,
            'messages_sent': [],
            'started_at': datetime.now(timezone.utc).isoformat(),
        })

    def _save_onboarding(self, chat_id: str):
        ONBOARDING_DIR.mkdir(exist_ok=True)
        path = self._onboarding_path(chat_id)
        data = self.onboarding.get(str(chat_id), {})
        try:
            with open(path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            log.error(f"Failed to save onboarding for {chat_id}: {e}")

    def get_onboarding_message(self, day: int, lang: str) -> str:
        """Return the onboarding message for a given day in the user's language."""
        lang_map = _ONBOARDING_MESSAGES.get(lang, _ONBOARDING_MESSAGES['en'])
        msg = lang_map.get(day)
        if msg:
            return msg
        fallback = _ONBOARDING_MESSAGES['en'].get(day)
        if fallback:
            return fallback
        return f"\U0001f4d6 Onboarding Day {day}/7\nCheck back tomorrow for the next lesson!"

    def get_onboarding_progress(self, chat_id: str) -> Dict[str, Any]:
        """Return dict of onboarding progress for a user."""
        prog = self._load_onboarding(chat_id)
        sub = self.get_subscriber(chat_id)
        joined = ''
        if sub:
            joined = sub.get('joined', '')
        days_since_join = 0
        if joined:
            try:
                joined_dt = datetime.fromisoformat(joined)
                days_since_join = (datetime.now(timezone.utc) - joined_dt).days
            except Exception:
                pass
        return {
            'day': prog.get('day', 1),
            'completed': prog.get('completed', False),
            'messages_sent': prog.get('messages_sent', []),
            'days_since_join': days_since_join,
        }

    def advance_onboarding(self, chat_id: str) -> Dict[str, Any]:
        """Move user to the next onboarding day and return updated progress."""
        prog = self._load_onboarding(str(chat_id))
        current_day = prog.get('day', 1)
        if current_day >= 7:
            prog['completed'] = True
        else:
            prog['day'] = current_day + 1
        self.onboarding[str(chat_id)] = prog
        self._save_onboarding(chat_id)
        return self.get_onboarding_progress(chat_id)

    def schedule_onboarding(self, bot_send_fn: callable) -> int:
        """Check which onboarding messages should be sent today and send them."""
        sent = 0
        now = datetime.now(timezone.utc)
        for chat_id, sub in self.subscribers.items():
            joined_str = sub.get('joined', '')
            if not joined_str:
                continue
            try:
                joined_dt = datetime.fromisoformat(joined_str)
            except Exception:
                continue
            days_since = (now - joined_dt).days
            if days_since < 1 or days_since > 7:
                continue
            prog = self._load_onboarding(chat_id)
            sent_days = prog.get('messages_sent', [])
            target_day = days_since
            if target_day in sent_days:
                continue
            if prog.get('completed', False):
                continue
            lang = sub.get('language', 'en')
            msg = self.get_onboarding_message(target_day, lang)
            try:
                bot_send_fn(chat_id, msg)
                sent += 1
            except Exception:
                continue
            sent_days.append(target_day)
            prog['messages_sent'] = sent_days
            if target_day >= 7:
                prog['completed'] = True
            self.onboarding[chat_id] = prog
            self._save_onboarding(chat_id)
        return sent

    @staticmethod
    def get_user_timezone_offset(language_code: str) -> float:
        """Detect timezone offset from language code."""
        return _TIMEZONE_OFFSETS.get(language_code, 0.0)

    # ------------------------------------------------------------------
    # C) Re-engagement System
    # ------------------------------------------------------------------

    def check_inactive_users(self, days_threshold: int = 7) -> List[str]:
        """Return list of chat_ids inactive for N days."""
        inactive = []
        now = datetime.now(timezone.utc)
        for chat_id, sub in self.subscribers.items():
            last_active_str = sub.get('last_active', sub.get('joined', ''))
            if not last_active_str:
                inactive.append(chat_id)
                continue
            try:
                last_active = datetime.fromisoformat(last_active_str)
            except Exception:
                inactive.append(chat_id)
                continue
            if (now - last_active).days >= days_threshold:
                inactive.append(chat_id)
        return inactive

    def get_re_engagement_message(self, level: int) -> str:
        """Return re-engagement message for a given inactivity level (1 or 2)."""
        return _RE_ENGAGEMENT_MESSAGES.get(level, _RE_ENGAGEMENT_MESSAGES[1])

    # ------------------------------------------------------------------
    # D) Referral Tracking (Enhanced)
    # ------------------------------------------------------------------

    def get_referral_stats(self, chat_id: str) -> Dict[str, Any]:
        """Return referral stats for a user."""
        ref = self.referrals.get(str(chat_id))
        if not ref:
            return {
                'referral_count': 0,
                'free_days_earned': 0,
                'referred_users': [],
                'code': None,
            }
        referred_users = ref.get('referred_users', [])
        return {
            'referral_count': len(referred_users),
            'free_days_earned': ref.get('free_days_earned', 0),
            'referred_users': referred_users,
            'code': ref.get('code'),
        }

    # ------------------------------------------------------------------
    # E) Growth Analytics
    # ------------------------------------------------------------------

    def track_interaction(self, chat_id: str):
        """Update last_active timestamp for a user."""
        with self._lock:
            sub = self.subscribers.get(str(chat_id))
            if sub:
                sub['last_active'] = datetime.now(timezone.utc).isoformat()
                self._save_state()

    def get_growth_analytics(self) -> Dict[str, Any]:
        """Compute and return growth analytics from subscriber data."""
        now = datetime.now(timezone.utc)
        today = now.strftime('%Y-%m-%d')
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)

        total_users = len(self.subscribers)
        vip_count = sum(1 for s in self.subscribers.values()
                        if s.get('tier') == 'VIP' and not self._is_expired(s))

        new_today = 0
        active_7d = 0
        active_30d = 0
        language_distribution: Dict[str, int] = {}

        for sub in self.subscribers.values():
            lang = sub.get('language', 'en')
            language_distribution[lang] = language_distribution.get(lang, 0) + 1

            joined_str = sub.get('joined', '')
            if joined_str:
                try:
                    joined_dt = datetime.fromisoformat(joined_str)
                    if joined_dt.strftime('%Y-%m-%d') == today:
                        new_today += 1
                except Exception:
                    pass

            last_active_str = sub.get('last_active', sub.get('joined', ''))
            if last_active_str:
                try:
                    last_active = datetime.fromisoformat(last_active_str)
                    if last_active >= seven_days_ago:
                        active_7d += 1
                    if last_active >= thirty_days_ago:
                        active_30d += 1
                except Exception:
                    pass

        vip_pct = round((vip_count / total_users * 100), 1) if total_users > 0 else 0.0
        conversion_rate = round((vip_count / total_users * 100), 1) if total_users > 0 else 0.0

        referral_count = sum(
            len(ref.get('referred_users', []))
            for ref in self.referrals.values()
        )

        analytics = {
            'total_users': total_users,
            'new_today': new_today,
            'active_7d': active_7d,
            'active_30d': active_30d,
            'vip_count': vip_count,
            'vip_pct': vip_pct,
            'language_distribution': language_distribution,
            'conversion_rate': conversion_rate,
            'referral_count': referral_count,
            'computed_at': now.isoformat(),
        }

        with self._lock:
            self.growth_data['daily_active_7d'][today] = active_7d
            self.growth_data['daily_active_30d'][today] = active_30d
            self.growth_data['last_computed'] = now.isoformat()
            self._save_state()

        return analytics

    def format_growth_report(self) -> str:
        """Return a formatted growth report string for admin."""
        g = self.get_growth_analytics()
        lang_dist = g['language_distribution']
        top_langs = sorted(lang_dist.items(), key=lambda x: x[1], reverse=True)[:5]
        lang_lines = '\n'.join(f"  {code}: {count}" for code, count in top_langs)

        return (
            f"\U0001f4c8 GROWTH REPORT\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"Total Users    : {g['total_users']}\n"
            f"New Today      : {g['new_today']}\n"
            f"Active (7d)    : {g['active_7d']}\n"
            f"Active (30d)   : {g['active_30d']}\n"
            f"VIP Count      : {g['vip_count']} ({g['vip_pct']}%)\n"
            f"Conversion     : {g['conversion_rate']}%\n"
            f"Referrals      : {g['referral_count']}\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"Top Languages:\n"
            f"{lang_lines}\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        )

    def get_daily_growth(self) -> int:
        """Return number of new users who joined today."""
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        count = 0
        for sub in self.subscribers.values():
            joined_str = sub.get('joined', '')
            if joined_str:
                try:
                    if datetime.fromisoformat(joined_str).strftime('%Y-%m-%d') == today:
                        count += 1
                except Exception:
                    pass
        return count


_subs_manager: Optional[SubscriptionManager] = None
_lock = threading.Lock()


def get_subscription_manager() -> SubscriptionManager:
    global _subs_manager
    if _subs_manager is None:
        with _lock:
            if _subs_manager is None:
                _subs_manager = SubscriptionManager()
    return _subs_manager


ADMIN_COMMANDS = """
\U0001f6e1\ufe0f ADMIN COMMANDS
/addvip {chat_id} {days} \u2014 Add VIP for N days
/removevip {chat_id} \u2014 Remove VIP
/subscribers \u2014 List all subscribers
/revenue \u2014 Total revenue
/broadcast {msg} \u2014 Message all VIP
/extend {chat_id} {days} \u2014 Extend subscription
/pending \u2014 Show pending payments
/verify {chat_id} \u2014 Verify payment & grant VIP
/reject {chat_id} \u2014 Reject payment claim
/setlang {chat_id} {lang} \u2014 Set language
/growth \u2014 Growth analytics report
/referralstats {chat_id} \u2014 Referral stats
/inactive {days} \u2014 List inactive users
/onboardstatus {chat_id} \u2014 Onboarding progress
"""


def handle_admin_command(command: str, args: List[str], bot_send: callable) -> str:
    """Handle admin Telegram commands."""
    mgr = get_subscription_manager()

    if command == '/addvip' and len(args) >= 2:
        chat_id = args[0]
        try:
            days = int(args[1])
        except ValueError:
            return "Usage: /addvip {chat_id} {days}"
        name = args[2] if len(args) > 2 else 'vip_user'
        sub = mgr.add_subscriber(chat_id, name, 'VIP', days)
        return f"\u2705 VIP added: {name} ({chat_id}) for {days} days\nExpires: {sub['expires'][:10]}"

    elif command == '/removevip' and len(args) >= 1:
        chat_id = args[0]
        if mgr.remove_subscriber(chat_id):
            return f"\u2705 Removed: {chat_id}"
        return f"\u274c Subscriber not found: {chat_id}"

    elif command == '/extend' and len(args) >= 2:
        chat_id = args[0]
        try:
            days = int(args[1])
        except ValueError:
            return "Usage: /extend {chat_id} {days}"
        if mgr.extend_subscription(chat_id, days):
            return f"\u2705 Extended {chat_id} by {days} days"
        return f"\u274c Subscriber not found: {chat_id}"

    elif command == '/subscribers':
        return mgr.format_subscriber_list()

    elif command == '/revenue':
        return mgr.format_revenue_message()

    elif command == '/broadcast' and len(args) >= 1:
        msg = ' '.join(args)
        sent = mgr.broadcast_to_vip(msg, bot_send)
        return f"\u2705 Broadcast sent to {sent} VIP subscribers"

    elif command == '/pending':
        pending = mgr.get_pending_payments()
        if not pending:
            return "No pending payments."
        lines = [f"\U0001f4b3 PENDING PAYMENTS ({len(pending)})"]
        for p in pending:
            lines.append(
                f"  {p.get('name', '?')} ({p['chat_id']}) "
                f"\u20b9{p.get('amount', 0):.0f} "
                f"tx: {p.get('transaction_id', '?')[:12]}..."
            )
        return '\n'.join(lines)

    elif command == '/verify' and len(args) >= 1:
        chat_id = args[0]
        result = mgr.verify_and_welcome(chat_id)
        if result:
            welcome = result.get('welcome_message', '')
            if bot_send and welcome:
                try:
                    bot_send(chat_id, welcome)
                except Exception as e:
                    log.warning(f"Failed to send welcome to {chat_id}: {e}")
            return (
                f"\u2705 VIP GRANTED: {chat_id}\n"
                f"Amount: \u20b9{result['amount']:.0f}\n"
                f"Expires: {result['subscriber']['expires'][:10]}\n"
                f"Welcome message sent."
            )
        return f"\u274c No pending payment for: {chat_id}"

    elif command == '/reject' and len(args) >= 1:
        chat_id = args[0]
        if mgr.reject_payment(chat_id):
            return f"\u2705 Payment rejected: {chat_id}"
        return f"\u274c No pending payment for: {chat_id}"

    elif command == '/setlang' and len(args) >= 2:
        chat_id = args[0]
        lang = args[1]
        if mgr.set_language(chat_id, lang):
            return f"\u2705 Language set: {chat_id} -> {lang}"
        return f"\u274c Failed to set language for {chat_id}"

    elif command == '/growth':
        return mgr.format_growth_report()

    elif command == '/referralstats' and len(args) >= 1:
        chat_id = args[0]
        stats = mgr.get_referral_stats(chat_id)
        return (
            f"\U0001f517 REFERRAL STATS: {chat_id}\n"
            f"Code: {stats['code'] or 'N/A'}\n"
            f"Referrals: {stats['referral_count']}\n"
            f"Free Days: {stats['free_days_earned']}\n"
            f"Referred: {len(stats['referred_users'])} users"
        )

    elif command == '/inactive':
        threshold = int(args[0]) if args else 7
        inactive = mgr.check_inactive_users(threshold)
        if not inactive:
            return f"\u2705 No users inactive for {threshold}+ days."
        lines = [f"\U0001f4a4 INACTIVE USERS ({len(inactive)}) >={threshold}d"]
        for cid in inactive[:20]:
            name = mgr.get_subscriber(cid).get('name', '?') if mgr.get_subscriber(cid) else '?'
            lines.append(f"  {name} ({cid})")
        if len(inactive) > 20:
            lines.append(f"  ... and {len(inactive)-20} more")
        return '\n'.join(lines)

    elif command == '/onboardstatus' and len(args) >= 1:
        chat_id = args[0]
        prog = mgr.get_onboarding_progress(chat_id)
        return (
            f"\U0001f4d6 ONBOARDING: {chat_id}\n"
            f"Day: {prog['day']}/7\n"
            f"Completed: {prog['completed']}\n"
            f"Messages sent: {len(prog['messages_sent'])}\n"
            f"Days since join: {prog['days_since_join']}"
        )

    return "Unknown admin command"


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    if '--test' in sys.argv:
        print("=" * 60)
        print("  SUBSCRIPTION MANAGER - TEST")
        print("=" * 60)

        sm = SubscriptionManager()

        sm.add_subscriber('123456', 'test_user', 'VIP', 30)
        sub = sm.get_subscriber('123456')
        print(f"  Sub added: {sub['name']} tier={sub['tier']} expires={sub['expires'][:10]}")
        print(f"  Is VIP: {sm.is_vip('123456')}")
        print(f"  Is VIP (unknown): {sm.is_vip('999')}")

        sm.add_subscriber('789012', 'vip2', 'VIP', 5)
        print(f"  VIP count: {sm.get_subscriber_count()['vip']}")

        expiring = sm.get_expiring_soon(7)
        print(f"  Expiring soon (7d): {len(expiring)}")

        signal = {'symbol': 'XAUUSD', 'direction': 'BULLISH', 'decision': 'EXECUTE', 'score': 85}
        routed = sm.route_signal('123456', signal)
        print(f"  VIP route: {routed['channel']} full={routed['send_full']}")

        routed_free = sm.route_signal('999', signal)
        print(f"  Free route: {routed_free['channel']} delay={routed_free['delay_seconds']}s")

        rev = sm.get_revenue_report()
        print(f"  Revenue: ${rev['total_revenue']:.2f}")

        sm.remove_subscriber('789012')
        print(f"  After remove: {sm.get_subscriber_count()}")

        admin_msg = handle_admin_command('/subscribers', [], lambda c, m: None)
        print(f"  Admin sub list: {admin_msg[:50]}...")

        print(f"\n  {ADMIN_COMMANDS}")

        print("\n" + "=" * 60)

    elif '--test-onboarding' in sys.argv:
        print("=" * 60)
        print("  ONBOARDING SEQUENCE - TEST")
        print("=" * 60)

        sm = SubscriptionManager()
        msg = sm.handle_start('555000', 'TestUser', 'en')
        print(f"  Welcome message length: {len(msg)} chars")
        print(f"  Welcome (first 60): {msg[:60]}...")

        for day in range(1, 8):
            eng = sm.get_onboarding_message(day, 'en')
            hin = sm.get_onboarding_message(day, 'hi')
            print(f"  Day {day}: EN={len(eng)}chars HI={len(hin)}chars")

        prog = sm.get_onboarding_progress('555000')
        print(f"  Onboarding progress: day={prog['day']} completed={prog['completed']}")

        sm.advance_onboarding('555000')
        prog = sm.get_onboarding_progress('555000')
        print(f"  After advance: day={prog['day']}")

        inactive = sm.check_inactive_users(0)
        print(f"  Inactive (0d threshold): {len(inactive)}")

        ana = sm.get_growth_analytics()
        print(f"  Growth: total={ana['total_users']} vip={ana['vip_count']}")

        report = sm.format_growth_report()
        print(f"  Growth report lines: {len(report.split(chr(10)))}")

        stats = sm.get_referral_stats('555000')
        print(f"  Referral stats: {stats}")

        print("\n" + "=" * 60)

    elif '--daemon' in sys.argv:
        sm = get_subscription_manager()
        print("Subscription manager daemon running...")
        try:
            while True:
                expired = sm.check_expired()
                if expired:
                    log.info(f"Expired {len(expired)} subscriptions")
                time.sleep(86400)
        except KeyboardInterrupt:
            pass
    else:
        print("Usage:")
        print("  python subscription_manager.py --test              # Run tests")
        print("  python subscription_manager.py --test-onboarding   # Test onboarding")
        print("  python subscription_manager.py --daemon            # Start daemon")
