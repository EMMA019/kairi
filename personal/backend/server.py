from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import subprocess
import os

app = FastAPI(title="Sentinel API Server")

# ==========================================
# CORS設定 (Reactからのアクセスを許可する)
# ==========================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 開発用
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# エンドポイント: AI Judge 実行
# ==========================================
@app.post("/api/ai-judge/{ticker}")
async def run_ai_judge(ticker: str):
    try:
        # server.py があるフォルダ（backend）の絶対パスを取得
        base_dir = os.path.dirname(os.path.abspath(__file__))
        # そこから scripts フォルダ内の ai_judge.py を指定
        script_path = os.path.join(base_dir, "scripts", "ai_judge.py")
        
        print(f"🚀 Running AI Judge for {ticker}...")
        print(f"📂 Script Path: {script_path}")
        
        # ファイルが存在するか念のためチェック
        if not os.path.exists(script_path):
            print(f"❌ File not found: {script_path}")
            raise HTTPException(status_code=404, detail=f"Script not found at {script_path}")

        # サブプロセスとしてスクリプトを実行
        result = subprocess.run(
            ["python", script_path, ticker],
            capture_output=True, 
            text=True, 
            check=True
        )
        print(f"✅ Completed for {ticker}")
        
        return {
            "status": "success", 
            "message": f"{ticker} analysis completed", 
            "output": result.stdout
        }
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Script failed: {e.stderr}")
        raise HTTPException(status_code=500, detail=f"Script failed: {e.stderr}")
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))