from __future__ import annotations

import json
from pathlib import Path


class MemoryTools:
    def __init__(self, agents_memory_dir: Path | None = None) -> None:
        self.agents_memory_dir = agents_memory_dir or Path(__file__).resolve().parents[2] / "data" / "agents"

    def get_agent_memory(self, args: dict) -> dict:
        agent = str(args.get("agent", "")).strip()
        limit = int(args.get("limit", 10))

        if not agent:
            # Вернуть краткую сводку по всем агентам
            result = {}
            if self.agents_memory_dir.exists():
                for mem_file in sorted(self.agents_memory_dir.glob("*-memory.json")):
                    name = mem_file.stem.replace("-memory", "")
                    try:
                        data = json.loads(mem_file.read_text(encoding="utf-8"))
                        history = data.get("chat_history", [])
                        result[name] = {
                            "total_records": len(history),
                            "last_updated": data.get("updated_at"),
                            "last_task": next(
                                (m["content"] for m in reversed(history) if m.get("role") == "user"),
                                None,
                            ),
                        }
                    except Exception:
                        pass
            return {"agents": result}

        mem_file = self.agents_memory_dir / f"{agent}-memory.json"
        if not mem_file.exists():
            return {"agent": agent, "chat_history": [], "message": "Память агента пуста"}

        try:
            data = json.loads(mem_file.read_text(encoding="utf-8"))
        except Exception as e:
            return {"agent": agent, "error": str(e)}

        history = data.get("chat_history", [])
        return {
            "agent": agent,
            "total_records": len(history),
            "last_updated": data.get("updated_at"),
            "chat_history": history[-limit:],
        }
