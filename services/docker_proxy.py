"""
Docker Proxy API — 最小権限のDocker操作プロキシ
AI（sandbox）からのDocker操作を、引数を受け付けない固定エンドポイントに限定する。

【セキュリティ設計】
- AIから渡せるパラメータはゼロ（パスもコマンドもフラグも固定）
- subprocess.run は配列形式（bash -c を経由しない）
- 127.0.0.1 にバインド（外部からのアクセスを完全遮断）
"""
import subprocess
from flask import Flask, jsonify

app = Flask(__name__)

# 絶対パスで固定。AIからの入力は一切受け付けない
FIXED_COMPOSE_PATH = r"D:\program\chat\output\main\docker-compose.yml"
FIXED_WORKSPACE = r"D:\program\chat\output\main"


@app.route("/api/docker/up", methods=["POST"])
def docker_up():
    """docker compose up -d を実行"""
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", FIXED_COMPOSE_PATH, "up", "-d"],
            capture_output=True, text=True, timeout=120,
            cwd=FIXED_WORKSPACE
        )
        return jsonify({
            "stdout": result.stdout,
            "stderr": result.stderr,
            "code": result.returncode
        })
    except subprocess.TimeoutExpired:
        return jsonify({"stdout": "", "stderr": "タイムアウト(120秒)", "code": -1})
    except Exception as e:
        return jsonify({"stdout": "", "stderr": str(e), "code": -1})


@app.route("/api/docker/down", methods=["POST"])
def docker_down():
    """docker compose down を実行"""
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", FIXED_COMPOSE_PATH, "down"],
            capture_output=True, text=True, timeout=60,
            cwd=FIXED_WORKSPACE
        )
        return jsonify({
            "stdout": result.stdout,
            "stderr": result.stderr,
            "code": result.returncode
        })
    except subprocess.TimeoutExpired:
        return jsonify({"stdout": "", "stderr": "タイムアウト(60秒)", "code": -1})
    except Exception as e:
        return jsonify({"stdout": "", "stderr": str(e), "code": -1})


@app.route("/api/docker/status", methods=["GET"])
def docker_status():
    """docker compose ps でコンテナ状態を確認"""
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", FIXED_COMPOSE_PATH, "ps"],
            capture_output=True, text=True, timeout=15,
            cwd=FIXED_WORKSPACE
        )
        return jsonify({"stdout": result.stdout})
    except subprocess.TimeoutExpired:
        return jsonify({"stdout": "タイムアウト(15秒)"})
    except Exception as e:
        return jsonify({"stdout": str(e)})


if __name__ == "__main__":
    # localhostのみバインド。sandboxコンテナからは host.docker.internal でアクセス
    app.run(host="127.0.0.1", port=18080, debug=False)