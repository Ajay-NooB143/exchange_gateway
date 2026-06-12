import asyncio
import aiohttp
from datetime import datetime

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd"
MEMPOOL_URL = "https://mempool.space/api/v1/fees/recommended"

async def fetch_endpoint(session, url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        async with session.get(url, headers=headers, timeout=10) as response:
            if response.status == 200:
                return await response.json()
            return {"error": f"HTTP {response.status}"}
    except Exception as e:
        return {"error": str(e)}

async def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Pinging public API endpoints concurrently...")
    
    async with aiohttp.ClientSession() as session:
        crypto_task = fetch_endpoint(session, COINGECKO_URL)
        mempool_task = fetch_endpoint(session, MEMPOOL_URL)
        
        crypto_data, mempool_data = await asyncio.gather(crypto_task, mempool_task)
        
        print("\n" + "="*45)
        print("📊 LIVE CONSOLIDATED MARKET FEED")
        print("="*45)
        
        if "error" not in crypto_data:
            btc_usd = crypto_data.get('bitcoin', {}).get('usd', 'N/A')
            eth_usd = crypto_data.get('ethereum', {}).get('usd', 'N/A')
            print(f"🪙 Bitcoin (BTC):  ${btc_usd:,} USD")
            print(f"🪙 Ethereum (ETH): ${eth_usd:,} USD")
        else:
            print(f"❌ Crypto Feed Error: {crypto_data['error']}")
            
        print("-"*45)
        
        if "error" not in mempool_data:
            print("🚀 Recommended BTC Network Fees (sat/vB):")
            print(f"  • Fastest Fee:  {mempool_data.get('fastestFee')} sat/vB")
            print(f"  • Half Hour:    {mempool_data.get('halfHourFee')} sat/vB")
            print(f"  • Hour Fee:     {mempool_data.get('hourFee')} sat/vB")
        else:
            print(f"❌ Mempool Feed Error: {mempool_data['error']}")
            
        print("="*45 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
