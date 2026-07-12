import os

EXCLUDED_DIR_NAMES = {".git", ".dart_tool", ".idea", "build", "node_modules", ".gradle", ".vscode", "Pods", "DerivedData", ".cxx"}
EXCLUDED_FILE_NAMES = {".DS_Store", "local.properties"}
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024


class FileCollector:
    @staticmethod
    def collect(project_root: str) -> dict:
        result = {}
        for dirpath, dirnames, filenames in os.walk(project_root):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIR_NAMES]
            for fname in filenames:
                if fname in EXCLUDED_FILE_NAMES: continue
                abs_path = os.path.join(dirpath, fname)
                try:
                    size = os.path.getsize(abs_path)
                except OSError: continue
                if fname.endswith(".bak"): continue
                if size > MAX_FILE_SIZE_BYTES or size == 0: continue
                rel = os.path.relpath(abs_path, project_root)
                result[rel.replace(os.sep, "/")] = abs_path
        return result

    @staticmethod
    def summarize(files: dict) -> tuple:
        total = sum(os.path.getsize(p) for p in files.values())
        return len(files), total

    @staticmethod
    def format_bytes(n: int) -> str:
        if n < 1024: return f"{n} B"
        if n < 1024 * 1024: return f"{n/1024:.1f} KB"
        return f"{n/(1024*1024):.1f} MB"
