from __future__ import annotations

import re
import shutil
from pathlib import Path

from src.infra.errors import ToolExecutionError
from src.safety.path_guard import PathGuard


class FileTools:
    def __init__(self, path_guard: PathGuard) -> None:
        self.path_guard = path_guard

    def create_file(self, args: dict[str, object]) -> dict[str, object]:
        path = Path(str(args["path"])).expanduser().resolve()
        content_value = args.get("content", "")
        content = "" if content_value is None else str(content_value)
        overwrite_value = args.get("overwrite", False)
        overwrite = overwrite_value if isinstance(overwrite_value, bool) else str(overwrite_value).strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
        }

        if path.exists() and not overwrite:
            raise ToolExecutionError(f"Файл уже существует: {path}")

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {
            "path": str(path),
            "created": True,
            "bytes_written": len(content.encode("utf-8")),
            "overwrite": overwrite,
        }

    def list_directory(self, args: dict[str, object]) -> dict[str, object]:
        path = self.path_guard.normalize(str(args["path"]))
        if not path.exists() or not path.is_dir():
            raise ToolExecutionError(f"Директория не найдена: {path}")
        items = []
        for item in sorted(path.iterdir(), key=lambda value: value.name.lower()):
            items.append({"name": item.name, "is_dir": item.is_dir()})
        return {"path": str(path), "items": items}

    def read_text_file(self, args: dict[str, object]) -> dict[str, object]:
        path = self.path_guard.normalize(str(args["path"]))
        if not path.exists() or not path.is_file():
            raise ToolExecutionError(f"Файл не найден: {path}")
        return {"path": str(path), "content": path.read_text(encoding="utf-8", errors="ignore")[:12000]}

    def file_exists(self, args: dict[str, object]) -> dict[str, object]:
        path = self.path_guard.normalize(str(args["path"]))
        return {"path": str(path), "exists": path.exists()}

    def get_file_info(self, args: dict[str, object]) -> dict[str, object]:
        path = self.path_guard.normalize(str(args["path"]))
        if not path.exists():
            raise ToolExecutionError(f"Путь не найден: {path}")
        stat = path.stat()
        return {
            "path": str(path),
            "is_dir": path.is_dir(),
            "size": stat.st_size,
        }

    def create_directory(self, args: dict[str, object]) -> dict[str, object]:
        path = self.path_guard.normalize(str(args["path"]))
        already_existed = path.exists()
        path.mkdir(parents=True, exist_ok=True)
        return {"path": str(path), "created": True, "already_existed": already_existed}

    def copy_file(self, args: dict[str, object]) -> dict[str, object]:
        source = self.path_guard.normalize(str(args["source"]))
        destination = self.path_guard.normalize(str(args["destination"]))
        if not source.exists() or not source.is_file():
            raise ToolExecutionError(f"Файл-источник не найден: {source}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return {"source": str(source), "destination": str(destination), "copied": True}

    def move_file(self, args: dict[str, object]) -> dict[str, object]:
        source = self.path_guard.normalize(str(args["source"]))
        destination = self.path_guard.normalize(str(args["destination"]))
        if not source.exists() or not source.is_file():
            raise ToolExecutionError(f"Файл-источник не найден: {source}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        return {"source": str(source), "destination": str(destination), "moved": True}

    def delete_file(self, args: dict[str, object]) -> dict[str, object]:
        path = self.path_guard.normalize(str(args["path"]))
        if not path.exists() or not path.is_file():
            raise ToolExecutionError(f"Файл не найден: {path}")
        path.unlink()
        return {"path": str(path), "deleted": True}

    def read_multiple_files(self, args: dict[str, object]) -> dict[str, object]:
        paths_value = args.get("paths", [])
        if not isinstance(paths_value, list):
            raise ToolExecutionError("Параметр paths должен быть списком путей")

        results = []
        errors = []

        for path_str in paths_value:
            try:
                path = self.path_guard.normalize(str(path_str))
                if not path.exists() or not path.is_file():
                    errors.append({"path": str(path), "error": "Файл не найден"})
                    continue
                content = path.read_text(encoding="utf-8", errors="ignore")[:12000]
                results.append({"path": str(path), "content": content})
            except Exception as e:
                errors.append({"path": str(path_str), "error": str(e)})

        return {
            "results": results,
            "errors": errors,
            "total": len(paths_value),
            "success": len(results),
            "failed": len(errors)
        }

    def patch_file(self, args: dict[str, object]) -> dict[str, object]:
        """Заменить точный блок текста old_str на new_str.

        Аналог инструмента edit в Cursor/Windsurf.
        old_str должен однозначно идентифицировать место — включай достаточно контекстных строк.
        """
        path = self.path_guard.normalize(str(args["path"]))
        if not path.exists() or not path.is_file():
            raise ToolExecutionError(f"Файл не найден: {path}")

        old_str = str(args.get("old_str", ""))
        new_str = str(args.get("new_str", ""))

        if not old_str:
            raise ToolExecutionError("Параметр old_str не может быть пустым")

        content = path.read_text(encoding="utf-8")
        count = content.count(old_str)

        if count == 0:
            raise ToolExecutionError(
                f"Строка old_str не найдена в файле {path.name}. "
                "Сначала прочитай файл через read_text_file и используй точный текст."
            )
        if count > 1:
            raise ToolExecutionError(
                f"old_str встречается {count} раз — добавь больше контекста, чтобы выбрать уникальный блок."
            )

        new_content = content.replace(old_str, new_str, 1)
        path.write_text(new_content, encoding="utf-8")

        old_lines = old_str.count("\n") + 1
        new_lines = new_str.count("\n") + 1
        return {
            "path": str(path),
            "patched": True,
            "lines_removed": old_lines,
            "lines_added": new_lines,
        }

    def insert_lines(self, args: dict[str, object]) -> dict[str, object]:
        """Вставить текст после указанной строки (1-based). after_line=0 — вставить в начало файла."""
        path = self.path_guard.normalize(str(args["path"]))
        if not path.exists() or not path.is_file():
            raise ToolExecutionError(f"Файл не найден: {path}")

        try:
            after_line = int(str(args.get("after_line", 0)))
        except ValueError:
            raise ToolExecutionError("after_line должен быть целым числом")

        text = str(args.get("text", ""))
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

        if after_line < 0 or after_line > len(lines):
            raise ToolExecutionError(
                f"after_line={after_line} вне диапазона (файл содержит {len(lines)} строк)"
            )

        insert_lines = text.splitlines(keepends=True)
        if insert_lines and not insert_lines[-1].endswith("\n"):
            insert_lines[-1] += "\n"

        new_lines = lines[:after_line] + insert_lines + lines[after_line:]
        path.write_text("".join(new_lines), encoding="utf-8")

        return {
            "path": str(path),
            "inserted_after_line": after_line,
            "lines_inserted": len(insert_lines),
            "total_lines": len(new_lines),
        }

    def delete_lines(self, args: dict[str, object]) -> dict[str, object]:
        """Удалить строки с from_line по to_line включительно (1-based)."""
        path = self.path_guard.normalize(str(args["path"]))
        if not path.exists() or not path.is_file():
            raise ToolExecutionError(f"Файл не найден: {path}")

        try:
            from_line = int(str(args["from_line"]))
            to_line = int(str(args["to_line"]))
        except (KeyError, ValueError):
            raise ToolExecutionError("from_line и to_line должны быть целыми числами")

        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        total = len(lines)

        if from_line < 1 or to_line > total or from_line > to_line:
            raise ToolExecutionError(
                f"Диапазон [{from_line}, {to_line}] невалиден (файл содержит {total} строк)"
            )

        removed = lines[from_line - 1 : to_line]
        new_lines = lines[: from_line - 1] + lines[to_line:]
        path.write_text("".join(new_lines), encoding="utf-8")

        return {
            "path": str(path),
            "deleted": True,
            "from_line": from_line,
            "to_line": to_line,
            "lines_deleted": len(removed),
            "total_lines_remaining": len(new_lines),
        }

    def search_in_file(self, args: dict[str, object]) -> dict[str, object]:
        """Найти все вхождения паттерна в файле. Возвращает строки с номерами и контекстом."""
        path = self.path_guard.normalize(str(args["path"]))
        if not path.exists() or not path.is_file():
            raise ToolExecutionError(f"Файл не найден: {path}")

        pattern = str(args.get("pattern", ""))
        if not pattern:
            raise ToolExecutionError("Параметр pattern не может быть пустым")

        use_regex = str(args.get("use_regex", "false")).lower() in {"true", "1", "yes"}
        context_lines = min(int(str(args.get("context_lines", 2))), 10)

        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        matches = []

        for i, line in enumerate(lines):
            hit = re.search(pattern if use_regex else re.escape(pattern), line)
            if hit:
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)
                matches.append({
                    "line": i + 1,
                    "text": line,
                    "context": [
                        {"line": j + 1, "text": lines[j]}
                        for j in range(start, end)
                    ],
                })

        return {
            "path": str(path),
            "pattern": pattern,
            "match_count": len(matches),
            "matches": matches[:50],
        }

    def search_in_directory(self, args: dict[str, object]) -> dict[str, object]:
        """Поиск паттерна по всем файлам в директории (grep-подобный).

        Параметры: path, pattern, use_regex?, file_glob? (например *.py), max_results?
        """
        root = self.path_guard.normalize(str(args["path"]))
        if not root.exists() or not root.is_dir():
            raise ToolExecutionError(f"Директория не найдена: {root}")

        pattern = str(args.get("pattern", ""))
        if not pattern:
            raise ToolExecutionError("Параметр pattern не может быть пустым")

        use_regex = str(args.get("use_regex", "false")).lower() in {"true", "1", "yes"}
        file_glob = str(args.get("file_glob", "*"))
        max_results = min(int(str(args.get("max_results", 50))), 200)
        compiled = re.compile(pattern if use_regex else re.escape(pattern))

        results = []
        for file_path in sorted(root.rglob(file_glob)):
            if not file_path.is_file():
                continue
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines()):
                if compiled.search(line):
                    results.append({
                        "file": str(file_path),
                        "line": i + 1,
                        "text": line.strip(),
                    })
                    if len(results) >= max_results:
                        return {
                            "root": str(root),
                            "pattern": pattern,
                            "match_count": len(results),
                            "truncated": True,
                            "matches": results,
                        }

        return {
            "root": str(root),
            "pattern": pattern,
            "match_count": len(results),
            "truncated": False,
            "matches": results,
        }

    def find_files(self, args: dict[str, object]) -> dict[str, object]:
        """Найти файлы по glob-паттерну внутри директории.

        Параметры: path, glob (например **/*.py), max_results?
        """
        root = self.path_guard.normalize(str(args["path"]))
        if not root.exists() or not root.is_dir():
            raise ToolExecutionError(f"Директория не найдена: {root}")

        glob_pattern = str(args.get("glob", "*"))
        max_results = min(int(str(args.get("max_results", 100))), 500)

        found = []
        for p in sorted(root.rglob(glob_pattern)):
            found.append({
                "path": str(p),
                "is_dir": p.is_dir(),
                "size": p.stat().st_size if p.is_file() else None,
            })
            if len(found) >= max_results:
                break

        return {
            "root": str(root),
            "glob": glob_pattern,
            "count": len(found),
            "truncated": len(found) >= max_results,
            "files": found,
        }

    def rename(self, args: dict[str, object]) -> dict[str, object]:
        """Переименовать файл или директорию."""
        source = self.path_guard.normalize(str(args["source"]))
        destination = self.path_guard.normalize(str(args["destination"]))

        if not source.exists():
            raise ToolExecutionError(f"Путь не найден: {source}")
        if destination.exists():
            raise ToolExecutionError(f"Путь уже существует: {destination}")

        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
        return {
            "source": str(source),
            "destination": str(destination),
            "renamed": True,
        }
