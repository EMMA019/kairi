from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os
from pathlib import Path
from typing import List
from fastapi.responses import StreamingResponse
import io
import zipfile
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

# 安全のため、特定のディレクトリ配下のみにファイル操作を制限する
ROOT_OUTPUT_DIR = Path("D:/program/chat/output")
ROOT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_WORKSPACE_DIR = ROOT_OUTPUT_DIR

# アクティブプロジェクトのワークスペースパス
_ACTIVE_WORKSPACE = str(BASE_WORKSPACE_DIR)

def get_workspace_dir() -> Path:
    """現在の動的なワークスペースディレクトリPathを取得"""
    global _ACTIVE_WORKSPACE
    if _ACTIVE_WORKSPACE:
        p = Path(_ACTIVE_WORKSPACE)
        p.mkdir(parents=True, exist_ok=True)
        return p
    return ROOT_OUTPUT_DIR

IGNORE_DIRS = {
    "venv", ".venv", "node_modules", ".git", "__pycache__",
    "dist", "build", ".next", ".nuxt", "coverage",
    ".vscode", "idea", "*.egg-info", ".tox",
    "cache", "storage", "data", "output", "uploads",
}

IGNORE_EXTS = {
    ".db", ".sqlite", ".sqlite3", ".pyc", ".pyo", ".png", ".jpg", ".jpeg",
    ".gif", ".ico", ".svg", ".webp", ".exe", ".dll", ".so", ".dylib",
    ".zip", ".tar", ".gz", ".7z", ".rar", ".pdf", ".mp3", ".mp4", ".mov",
}

def set_workspace_path(path: str):
    """アクティブなワークスペースパスを設定"""
    global _ACTIVE_WORKSPACE, BASE_WORKSPACE_DIR
    _ACTIVE_WORKSPACE = path
    BASE_WORKSPACE_DIR = Path(path)
    # ToolHandlerのBASE_WORKSPACE_DIRを更新
    try:
        import app.core.tools.handler as h
        h.BASE_WORKSPACE_DIR = Path(path)
    except Exception:
        pass

def get_current_workspace() -> str:
    """現在のワークスペースパスを取得"""
    return str(get_workspace_dir())

class FileRequest(BaseModel):
    path: str
    content: str

class SaveRequest(BaseModel):
    files: List[FileRequest]

@router.post("/workspace/save")
async def save_files(request: SaveRequest):
    """
    指定されたパスにファイルを保存する。
    ディレクトリ・トラバーサルを防ぐため、現在のワークスペース配下のみ許可。
    """
    saved_files = []
    ws_dir = get_workspace_dir()
    
    for file_req in request.files:
        # パスをサニタイズ（上位ディレクトリへの参照を禁止）
        safe_path = file_req.path.replace("..", "").lstrip("/\\")
        target_path = ws_dir / safe_path
        
        # 保存先ディレクトリを作成
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(file_req.content)
            saved_files.append(str(target_path))
            logger.info(f"ファイルを保存しました: {target_path}")
        except Exception as e:
            logger.error(f"ファイル保存エラー ({target_path}): {e}")
            raise HTTPException(status_code=500, detail=f"ファイル保存に失敗しました: {safe_path}")
            
    return {"success": True, "saved_files": saved_files, "base_dir": str(ws_dir)}

def get_workspace_files_text() -> str:
    """現在のワークスペース内の全テキストファイルを <file> タグでラップして返す（キャッシュ効率・高速化対応）"""
    ws_dir = get_workspace_dir()
    if not ws_dir.exists():
        return "ワークスペースは空です。"
    
    context = ""
    total_chars = 0
    max_total_chars = 100_000  # 最大100KBに制限してキャッシュ・通信効率を最大化
    max_file_chars = 50_000    # 1ファイルあたり最大50KB
    file_count = 0
    max_files = 30
    
    for root, dirs, files in os.walk(ws_dir):
        # 除外ディレクトリをスキップ
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
        
        for file in sorted(files):
            if file.startswith(".") or file == "__pycache__":
                continue
            ext = os.path.splitext(file)[1].lower()
            if ext in IGNORE_EXTS:
                continue
                
            file_path = Path(root) / file
            rel_path = file_path.relative_to(ws_dir).as_posix()
            
            try:
                if file_path.stat().st_size > 1_000_000:
                    context += f'<file path="{rel_path}">\n[サイズ超過ファイル ({file_path.stat().st_size} bytes): <read_file> で確認してください]\n</file>\n'
                    continue
                    
                content = file_path.read_text(encoding="utf-8")
                if len(content) > max_file_chars:
                    content = content[:max_file_chars] + f"\n... [{len(content) - max_file_chars}文字省略: 必要に応じて <read_file> で確認してください] ..."
                    
                if total_chars + len(content) > max_total_chars or file_count >= max_files:
                    context += f'<file path="{rel_path}">\n[ファイル上限・サイズ上限に到達: 必要に応じて <read_file> または <search_codebase> を使用してください]\n</file>\n'
                    continue
                    
                context += f'<file path="{rel_path}">\n{content}\n</file>\n'
                total_chars += len(content)
                file_count += 1
            except Exception:
                pass
    return context.strip() if context else "ワークスペースは空です。"

@router.get("/workspace/tree")
async def get_workspace_tree():
    """ワークスペース内のファイルツリーを返す"""
    ws_dir = get_workspace_dir()
    if not ws_dir.exists():
        return []
        
    def build_tree(dir_path: Path):
        tree = []
        for item in sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if item.name.startswith(".") or item.name in IGNORE_DIRS:
                continue
            if not item.is_dir() and item.suffix.lower() in IGNORE_EXTS:
                continue
                
            node = {
                "name": item.name,
                "path": str(item.relative_to(ws_dir)).replace("\\", "/"),
                "type": "directory" if item.is_dir() else "file"
            }
            if item.is_dir():
                node["children"] = build_tree(item)
            tree.append(node)
        return tree
        
    return build_tree(ws_dir)

@router.get("/workspace/file")
async def get_workspace_file(path: str):
    """ファイルの内容を返す"""
    ws_dir = get_workspace_dir()
    safe_path = path.replace("..", "").lstrip("/\\")
    target = ws_dir / safe_path
    
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
        
    try:
        content = target.read_text(encoding="utf-8")
        return {"content": content}
    except Exception as e:
        logger.error(f"Error reading file {path}: {e}")
        raise HTTPException(status_code=400, detail="Could not read file")

@router.get("/workspace/download")
async def download_workspace():
    """ワークスペース全体を .zip ファイルとしてダウンロードする"""
    ws_dir = get_workspace_dir()
    if not ws_dir.exists():
        raise HTTPException(status_code=404, detail="Workspace is empty")
        
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(ws_dir):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
            for file in files:
                if file.startswith(".") or file == "__pycache__":
                    continue
                ext = os.path.splitext(file)[1].lower()
                if ext in IGNORE_EXTS:
                    continue
                file_path = Path(root) / file
                rel_path = file_path.relative_to(ws_dir).as_posix()
                zf.write(file_path, arcname=str(rel_path))
                
    zip_buffer.seek(0)
    
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=workspace.zip"}
    )
