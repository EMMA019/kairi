import os
import subprocess
import logging
import time

from pathlib import Path

logger = logging.getLogger(__name__)

def git_snapshot(workspace_dir: str, message: str = "Auto-snapshot before AI modification") -> bool:
    """
    ワークスペース内でファイル変更が行われる直前に、自動でgitコミットを作成する。
    """
    work_path = Path(workspace_dir)
    if not work_path.exists() or not work_path.is_dir():
        logger.error(f"Snapshot failed: Directory not found -> {workspace_dir}")
        return False

    try:
        # .git ディレクトリが存在しない場合は初期化
        if not (work_path / ".git").exists():
            subprocess.run(
                ["git", "init"],
                cwd=str(work_path),
                check=True,
                capture_output=True,
                text=True
            )
            # 初期化直後はダミーコミットが必要な場合があるため、必要に応じて設定
            subprocess.run(
                ["git", "config", "user.email", "ai-agent@antigravity.local"],
                cwd=str(work_path),
                check=True
            )
            subprocess.run(
                ["git", "config", "user.name", "Antigravity Agent"],
                cwd=str(work_path),
                check=True
            )

        # 変更をすべてステージング
        subprocess.run(
            ["git", "add", "-A"],
            cwd=str(work_path),
            check=True,
            capture_output=True,
            text=True
        )

        # 変更があるか確認（空コミットを防ぐ）
        status_process = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(work_path),
            check=True,
            capture_output=True,
            text=True
        )

        if not status_process.stdout.strip():
            logger.info(f"No changes to snapshot in {workspace_dir}")
            return True # 変更がない場合は成功扱い

        # コミット実行
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=str(work_path),
            check=True,
            capture_output=True,
            text=True
        )
        logger.info(f"Git snapshot created in {workspace_dir}: {message}")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"Git snapshot failed in {workspace_dir}: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during git snapshot: {str(e)}")
        return False

class DockerSandbox:
    def __init__(self, session_id: str, workspace_dir: str):
        self.session_id = session_id
        self.container_name = f"ag_sandbox_{session_id}"
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.docker_workspace = self.workspace_dir.replace('\\', '/')
        self.use_host_fallback = False
        self._docker_unavailable = False
        self._ensure_container_running()

    def _ensure_container_running(self):
        """コンテナが起動しているか確認し、なければ起動する（失敗時はホスト実行フォールバックへ切替）"""
        try:
            res = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name={self.container_name}"],
                capture_output=True, text=True, check=True, timeout=25
            )
            if not res.stdout.strip():
                logger.info(f"Starting new Docker sandbox container: {self.container_name}")
                subprocess.run(["docker", "rm", "-f", self.container_name], capture_output=True, timeout=25)
                
                res_run = subprocess.run([
                    "docker", "run", "-d",
                    "--name", self.container_name,
                    "-v", f"{self.docker_workspace}:/workspace",
                    "-w", "/workspace",
                    "nikolaik/python-nodejs:python3.11-nodejs20",
                    "tail", "-f", "/dev/null"
                ], capture_output=True, text=True, timeout=120)  # 初回イメージpullを許容しつつ、デーモン無応答で固まらないように
                
                if res_run.returncode != 0:
                    raise Exception(f"Docker startup failed: {res_run.stderr}")
                time.sleep(1)
        except Exception as e:
            # セキュリティ: ホスト fallback は明示オプトイン時のみ
            allow_host = os.environ.get("ALLOW_HOST_FALLBACK", "").strip() in ("1", "true", "TRUE", "yes")
            if allow_host:
                logger.warning(f"Docker未検出のためホスト直接実行モードを使用します (ALLOW_HOST_FALLBACK=1): {e}")
                self.use_host_fallback = True
            else:
                logger.error(
                    f"Docker未検出/起動不可。ホスト実行は無効です。"
                    f"Dockerを起動するか ALLOW_HOST_FALLBACK=1 を設定してください: {e}"
                )
                self.use_host_fallback = False
                self._docker_unavailable = True

    def run_command(self, command: str, timeout: int = 60) -> str:
        """Run command in Docker (or host fallback).

        Child processes get a scrubbed env (no KEY/SECRET/TOKEN/PASSWORD).
        Timeouts return structured TOOL_TIMEOUT; exitCode and timedOut are independent.
        """
        from app.core.process_env import (
            scrubbed_environ,
            format_command_result,
            format_tool_timeout_result,
            resolve_command_timeout,
        )

        try:
            if getattr(self, "_docker_unavailable", False) and not self.use_host_fallback:
                return (
                    "❌ command unavailable: Docker missing and host fallback disabled. "
                    "Start Docker or set ALLOW_HOST_FALLBACK=1 for local dev only."
                )

            timeout = resolve_command_timeout(command, default=timeout)
            if timeout >= 300:
                logger.info(
                    "build/test timeout budget %ss: %s...",
                    timeout,
                    command[:50],
                )

            child_env = scrubbed_environ()

            if self.use_host_fallback:
                res = subprocess.run(
                    command,
                    shell=True,
                    cwd=self.workspace_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=child_env,
                )
            else:
                res = subprocess.run(
                    ["docker", "exec", self.container_name, "bash", "-c", command],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=child_env,
                )
            return format_command_result(
                stdout=res.stdout or "",
                stderr=res.stderr or "",
                exit_code=int(res.returncode if res.returncode is not None else 1),
                timed_out=False,
                command=command,
            )

        except subprocess.TimeoutExpired as e:
            partial_out = ""
            partial_err = ""
            try:
                if getattr(e, "stdout", None):
                    partial_out = (
                        e.stdout
                        if isinstance(e.stdout, str)
                        else e.stdout.decode("utf-8", "replace")
                    )
                if getattr(e, "stderr", None):
                    partial_err = (
                        e.stderr
                        if isinstance(e.stderr, str)
                        else e.stderr.decode("utf-8", "replace")
                    )
            except Exception:
                pass
            return format_tool_timeout_result(
                timeout_sec=timeout,
                command=command,
                partial_stdout=partial_out,
                partial_stderr=partial_err,
            )
        except Exception as e:
            return f"[ERROR] command execution exception: {e}"

    def read_file(self, file_path: str) -> str:
        """安全なファイル読み込み"""
        return safe_read_file(self.workspace_dir, file_path)
            
    def list_dir(self, dir_path: str = ".") -> str:
        """安全なディレクトリ一覧取得（ファイルタイプ・サイズ付き）"""
        return safe_list_dir(self.workspace_dir, dir_path)

def safe_read_file(workspace_dir: str, file_path: str) -> str:
    """安全なファイル読み込み（Docker非依存のフォールバック対応）"""
    try:
        target = resolve_workspace_target(workspace_dir, file_path)
    except ValueError:
        return "[エラー: ワークスペース外のファイルにはアクセスできません]"
    target_path = str(target)
        
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read()
            if len(content) > 50000:
                return "[エラー: ファイルが大きすぎます（50000文字以上）]"
            return content
    except FileNotFoundError:
        return f"[エラー: ファイルが見つかりません: {file_path}]"
    except Exception as e:
        return f"[エラー: ファイル読み込み失敗: {e}]"

def safe_list_dir(workspace_dir: str, dir_path: str = ".") -> str:
    """安全なディレクトリ一覧取得（Docker非依存のフォールバック対応）"""
    try:
        target = resolve_workspace_target(workspace_dir, dir_path or ".")
    except ValueError:
        return "[エラー: ワークスペース外のディレクトリにはアクセスできません]"
    target_path = str(target)
        
    try:
        if not os.path.exists(target_path):
            return f"[エラー: ディレクトリが見つかりません: {dir_path}]"
        if not os.path.isdir(target_path):
            return f"[エラー: 指定されたパスはディレクトリではありません: {dir_path}]"
            
        items = []
        for entry in os.scandir(target_path):
            if entry.name.startswith(".") or entry.name in ["node_modules", "__pycache__", "venv", ".venv"]:
                continue
            if entry.is_dir():
                try:
                    child_count = len(os.listdir(entry.path))
                except Exception:
                    child_count = "?"
                items.append(f"📁 {entry.name}/ ({child_count} items)")
            else:
                try:
                    size = entry.stat().st_size
                    if size < 1024:
                        size_str = f"{size} B"
                    elif size < 1024 * 1024:
                        size_str = f"{size / 1024:.1f} KB"
                    else:
                        size_str = f"{size / (1024 * 1024):.1f} MB"
                except Exception:
                    size_str = "? B"
                items.append(f"📄 {entry.name} ({size_str})")
        
        if not items:
            return "[ディレクトリは空です]"
        return "\n".join(sorted(items, key=lambda x: (0 if x.startswith("📁") else 1, x)))
    except Exception as e:
        return f"[エラー: ディレクトリ一覧取得失敗: {e}]"

def normalize_safe_path(base_dir_str: str, raw_path: str) -> str:
    """パストラバーサルや余分なプレフィックスを除去した安全な相対パスを返す（ファイル散乱完全防止）"""
    base_norm_f = base_dir_str.replace("\\", "/").lower().rstrip("/") + "/"
    base_norm_b = base_dir_str.replace("/", "\\").lower().rstrip("\\") + "\\"
    
    raw_clean = raw_path.strip()
    raw_norm_f = raw_clean.replace("\\", "/").lower()
    raw_norm_b = raw_clean.replace("/", "\\").lower()
    
    if raw_norm_f.startswith(base_norm_f):
        raw_clean = raw_clean[len(base_norm_f):]
    elif raw_norm_b.startswith(base_norm_b):
        raw_clean = raw_clean[len(base_norm_b):]
    elif os.path.isabs(raw_clean) or os.path.splitdrive(raw_clean)[0]:
        try:
            rel = Path(raw_clean).relative_to(Path(base_dir_str))
            raw_clean = str(rel)
        except Exception:
            raw_clean = os.path.splitdrive(raw_clean)[1]

    safe_path = raw_clean.replace("..", "").lstrip("/\\")
    prefixes_to_strip = ["workspace/", "workspace\\", "output/", "output\\"]
    
    base_parts = Path(base_dir_str).parts
    for i in range(len(base_parts)):
        sub_f = "/".join(base_parts[i:]) + "/"
        sub_b = "\\".join(base_parts[i:]) + "\\"
        prefixes_to_strip.extend([sub_f, sub_b])
        
    for _ in range(5):
        for pfx in prefixes_to_strip:
            if safe_path.startswith(pfx):
                safe_path = safe_path[len(pfx):]
            elif safe_path.lower().startswith(pfx.lower()):
                safe_path = safe_path[len(pfx):]
                
    if os.path.splitdrive(safe_path)[0]:
        safe_path = os.path.basename(safe_path)
    return safe_path


def resolve_workspace_target(workspace_dir: str | Path, raw_path: str) -> Path:
    """
    Resolve raw_path under workspace. Raises ValueError if it escapes.

    Uses normalize_safe_path then Path.resolve() + relative_to so Windows
    drive-absolute paths (C:/...) cannot escape via Path join semantics.
    """
    ws = Path(workspace_dir).expanduser().resolve()
    safe = normalize_safe_path(str(ws), raw_path or "")
    # Empty / "." means the workspace root itself
    target = (ws / safe).resolve() if safe not in ("", ".") else ws
    try:
        target.relative_to(ws)
    except ValueError as e:
        raise ValueError(f"path escapes workspace: {raw_path!r}") from e
    return target


def is_under_workspace(workspace_dir: str | Path, target: str | Path) -> bool:
    try:
        resolve_workspace_target(workspace_dir, str(target))
        return True
    except ValueError:
        # If target is already absolute under ws, compare resolved paths
        try:
            ws = Path(workspace_dir).expanduser().resolve()
            tgt = Path(target).expanduser().resolve()
            tgt.relative_to(ws)
            return True
        except Exception:
            return False

# グローバルなSandboxキャッシュ (セッションごと、最大20コンテナ)
_sandboxes: dict[str, DockerSandbox] = {}
_MAX_SANDBOXES = 20

def get_sandbox(session_id: str, workspace_dir: str) -> DockerSandbox:
    if session_id not in _sandboxes:
        # LRU: 古いサンドボックスを自動削除
        if len(_sandboxes) >= _MAX_SANDBOXES:
            oldest_key = next(iter(_sandboxes))
            cleanup_sandbox(oldest_key)
        _sandboxes[session_id] = DockerSandbox(session_id, workspace_dir)
    return _sandboxes[session_id]

def cleanup_sandbox(session_id: str) -> None:
    """セッション削除時にDockerコンテナとキャッシュを掃除する"""
    if session_id in _sandboxes:
        sandbox = _sandboxes.pop(session_id)
        try:
            subprocess.run(
                ["docker", "rm", "-f", sandbox.container_name],
                capture_output=True, timeout=10
            )
            logger.info(f"Dockerコンテナを削除しました: {sandbox.container_name}")
        except Exception as e:
            logger.warning(f"Dockerコンテナ削除失敗: {e}")
