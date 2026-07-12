import os, re, json
from typing import Dict

PROJECT_TYPE_LABELS = {
    "flutter": "Flutter", "android_native": "Android Studio (Native)",
    "react_native": "React Native", "unknown": "Unknown",
}
PROJECT_TYPE_ICONS = {
    "flutter": "🦋", "android_native": "🤖", "react_native": "⚛️", "unknown": "❓",
}


class ProjectAnalyzer:

    @staticmethod
    def resolve_project_root(extracted_dir: str) -> str:
        entries = [e for e in os.listdir(extracted_dir) if not e.startswith(".")]
        if len(entries) == 1 and os.path.isdir(os.path.join(extracted_dir, entries[0])):
            return os.path.join(extracted_dir, entries[0])
        return extracted_dir

    @staticmethod
    def analyze(project_root: str) -> Dict:
        root_names = set(os.listdir(project_root))
        has_pubspec = "pubspec.yaml" in root_names
        has_package_json = "package.json" in root_names
        has_build_gradle = "build.gradle" in root_names or "build.gradle.kts" in root_names
        has_settings_gradle = "settings.gradle" in root_names or "settings.gradle.kts" in root_names
        has_app_dir = "app" in root_names

        if has_pubspec:
            return ProjectAnalyzer._flutter(project_root, root_names)
        elif has_package_json and not has_build_gradle:
            pkg = open(os.path.join(project_root, "package.json"), encoding="utf-8", errors="ignore").read()
            if "react-native" in pkg:
                return ProjectAnalyzer._rn(project_root, root_names, pkg)
            return {"type": "unknown", "is_valid": False, "errors": ["Not a React Native project"], "warnings": [], "detected_info": {}, "root_entries": sorted(root_names)}
        elif has_build_gradle or has_settings_gradle or has_app_dir:
            return ProjectAnalyzer._native(project_root, root_names)
        return {"type": "unknown", "is_valid": False, "errors": ["Could not detect project type"], "warnings": [], "detected_info": {}, "root_entries": sorted(root_names)}

    @staticmethod
    def _flutter(root, root_names):
        errors, warnings, info = [], [], {}
        content = open(os.path.join(root, "pubspec.yaml"), encoding="utf-8", errors="ignore").read()
        m = re.search(r"^name:\s*(.+)$", content, re.MULTILINE)
        if m: info["package_name"] = m.group(1).strip()
        if "lib" not in root_names: errors.append("Missing lib/ directory")
        if "android" not in root_names: warnings.append("No android/ directory (will be auto-generated)")
        if not os.path.exists(os.path.join(root, "lib", "main.dart")): errors.append("lib/main.dart not found")
        return {"type": "flutter", "is_valid": not errors, "errors": errors, "warnings": warnings, "detected_info": info, "root_entries": sorted(root_names)}

    @staticmethod
    def _native(root, root_names):
        errors, warnings, info = [], [], {}
        if "gradlew" not in root_names: warnings.append("No gradlew found (will be generated)")
        gradle_content = None
        for p in (os.path.join(root, "app", "build.gradle"), os.path.join(root, "app", "build.gradle.kts")):
            if os.path.exists(p):
                gradle_content = open(p, encoding="utf-8", errors="ignore").read(); break
        if not gradle_content: errors.append("app/build.gradle not found")
        else:
            m = re.search(r'applicationId\s*[=]?\s*["\']([^"\']+)["\']', gradle_content)
            if m: info["application_id"] = m.group(1)
        return {"type": "android_native", "is_valid": not errors, "errors": errors, "warnings": warnings, "detected_info": info, "root_entries": sorted(root_names)}

    @staticmethod
    def _rn(root, root_names, pkg_content):
        errors, warnings, info = [], [], {}
        try:
            pkg = json.loads(pkg_content)
            if "name" in pkg: info["package_name"] = pkg["name"]
        except Exception: pass
        if "android" not in root_names: errors.append("android/ directory missing")
        return {"type": "react_native", "is_valid": not errors, "errors": errors, "warnings": warnings, "detected_info": info, "root_entries": sorted(root_names)}
