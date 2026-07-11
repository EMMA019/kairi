"""KV メモリ API ルーター"""
from fastapi import APIRouter, HTTPException

from app.models.memory import KVEntry
from app.core.kv_store import kv_store

router = APIRouter()


@router.get("/kv")
async def get_all_memories():
    """KVメモリ一覧を取得"""
    return {"memories": kv_store.get_all()}


@router.post("/kv")
async def add_memory(entry: KVEntry):
    """KVメモリを手動追加"""
    added = kv_store.add(entry.model_dump())
    return {"success": True, "entry": added}


@router.delete("/kv/{entry_id}")
async def delete_memory(entry_id: int):
    """KVメモリを削除"""
    if not kv_store.delete(entry_id):
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"success": True}
