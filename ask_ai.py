import sys
import requests

def ask_model(prompt):
    # 🔴 PASTE YOUR ACTUAL OPENROUTER API KEY BETWEEN THESE QUOTES:
    REAL_KEY = "your-actual-sk-or-v1-key-here"
    
    base_url = "https://openrouter.ai/api/v1/chat/completions"
    
    if not REAL_KEY or REAL_KEY.startswith("your-actual"):
        print("❌ Error: You forgot to replace the placeholder with your real OpenRouter key inside the script file!")
        return

    headers = {
        "Authorization": f"Bearer {REAL_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8080", # Required by some openrouter models
        "X-Title": "Terminal Client"
    }
    
    # We are using a lighter model profile here to make sure it runs 
    # even if your OpenRouter balance is under a few cents!
    data = {
        "model": "google/gemini-2.5-flash", 
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 300
    }

    try:
        response = requests.post(base_url, headers=headers, json=data)
        if response.status_code == 200:
            result = response.json()
            print("\n🤖 AI Response:")
            print(result['choices'][0]['message']['content'].strip())
        else:
            print(f"\n❌ OpenRouter Error ({response.status_code}):")
            print(response.text)
    except Exception as e:
        print(f"❌ Connection Failed: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 ask_ai.py 'Your question here'")
    else:
        user_prompt = " ".join(sys.argv[1:])
        ask_model(user_prompt)
