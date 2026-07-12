"""
Flutter Dependency Fixer — scans pubspec.yaml for outdated/incompatible
packages and applies safe version updates.
"""
import os
import re
import shutil
from typing import List, Dict, Tuple
from .base import FixResult, Severity

CATEGORY = "Flutter Dependencies"

# Known safe minimum versions for common packages.
# Format: package_name -> (min_version, recommended_version, reason)
KNOWN_VERSIONS: Dict[str, Tuple[str, str, str]] = {
    "hive":                    ("2.2.3",  "2.2.3",  "Stable, no breaking changes above this"),
    "hive_flutter":            ("1.1.0",  "1.1.0",  "Required for Flutter Hive init"),
    "hive_generator":          ("2.0.1",  "2.0.1",  "Matches hive 2.x adapter generation"),
    "build_runner":            ("2.4.0",  "2.4.8",  "Required for code generation"),
    "flutter_riverpod":        ("2.0.0",  "2.4.9",  "2.x API is stable and widely supported"),
    "riverpod_annotation":     ("2.0.0",  "2.3.3",  "Matches flutter_riverpod 2.x"),
    "go_router":               ("10.0.0", "13.0.0", "10+ has stable API"),
    "dio":                     ("5.0.0",  "5.4.0",  "5.x has null-safety and stable API"),
    "http":                    ("1.0.0",  "1.2.0",  "1.x is null-safe"),
    "shared_preferences":      ("2.0.0",  "2.2.2",  "2.x null-safe"),
    "path_provider":           ("2.0.0",  "2.1.2",  "2.x null-safe"),
    "flutter_secure_storage":  ("8.0.0",  "9.0.0",  "8+ supports Android Keystore"),
    "provider":                ("6.0.0",  "6.1.2",  "6.x is stable null-safe"),
    "get":                     ("4.6.0",  "4.6.6",  "4.6+ is stable"),
    "cached_network_image":    ("3.2.0",  "3.3.1",  "3.x null-safe"),
    "image_picker":            ("1.0.0",  "1.0.7",  "1.x null-safe"),
    "permission_handler":      ("11.0.0", "11.3.0", "11.x targets Android 13"),
    "url_launcher":            ("6.1.0",  "6.2.4",  "6.1+ null-safe"),
    "intl":                    ("0.18.0", "0.19.0", "0.18+ null-safe"),
    "flutter_animate":         ("4.0.0",  "4.5.0",  "4.x stable"),
    "lottie":                  ("2.0.0",  "3.0.0",  "2.x+ null-safe"),
    "sqflite":                 ("2.0.0",  "2.3.2",  "2.x null-safe"),
    "firebase_core":           ("2.0.0",  "2.25.4", "2.x null-safe Firebase"),
    "cloud_firestore":         ("4.0.0",  "4.15.5", "4.x null-safe"),
    "firebase_auth":           ("4.0.0",  "4.17.9", "4.x null-safe"),
    "google_fonts":            ("5.0.0",  "6.1.0",  "5.x+ null-safe"),
    "fl_chart":                ("0.60.0", "0.66.2", "0.60+ stable null-safe"),
    "webview_flutter":         ("4.0.0",  "4.4.2",  "4.x null-safe"),
    "connectivity_plus":       ("4.0.0",  "5.0.2",  "4.x+ null-safe"),
    "device_info_plus":        ("9.0.0",  "9.1.1",  "9.x null-safe"),
    "package_info_plus":       ("4.0.0",  "5.0.1",  "4.x null-safe"),
    "open_filex":              ("4.3.0",  "4.4.0",  "4.3+ supports Android 13"),
    "share_plus":              ("7.0.0",  "7.2.2",  "7.x null-safe"),
    "file_picker":             ("6.0.0",  "6.1.1",  "6.x null-safe"),
    "uuid":                    ("4.0.0",  "4.3.3",  "4.x null-safe Dart 3 compatible"),
    "rxdart":                  ("0.27.0", "0.27.7", "0.27+ null-safe"),
    "bloc":                    ("8.0.0",  "8.1.4",  "8.x null-safe"),
    "flutter_bloc":            ("8.0.0",  "8.1.6",  "8.x null-safe"),
    "equatable":               ("2.0.0",  "2.0.5",  "2.x null-safe"),
    "freezed":                 ("2.0.0",  "2.4.7",  "2.x null-safe"),
    "freezed_annotation":      ("2.0.0",  "2.4.2",  "Matches freezed 2.x"),
    "json_annotation":         ("4.8.0",  "4.8.1",  "4.8+ Dart 3 compatible"),
    "json_serializable":       ("6.7.0",  "6.7.1",  "6.7+ Dart 3 compatible"),
    "retrofit":                ("4.0.0",  "4.1.0",  "4.x null-safe"),
    "dartz":                   ("0.10.0", "0.10.1", "0.10+ null-safe"),
    "get_it":                  ("7.6.0",  "7.6.7",  "7.6+ null-safe"),
    "injectable":              ("2.3.0",  "2.3.2",  "2.3+ Dart 3 compatible"),
    "shimmer":                 ("3.0.0",  "3.0.0",  "3.x null-safe"),
    "fluttertoast":            ("8.2.0",  "8.2.4",  "8.2+ null-safe"),
    "encrypt":                 ("5.0.0",  "5.0.3",  "5.x null-safe"),
    "crypto":                  ("3.0.0",  "3.0.3",  "3.x null-safe"),
    "archive":                 ("3.4.0",  "3.4.10", "3.4+ stable"),
    "path":                    ("1.8.0",  "1.8.3",  "1.8+ stable"),
}

# Packages known to have breaking changes or to be deprecated
DEPRECATED_PACKAGES: Dict[str, str] = {
    "pedantic": "Replaced by flutter_lints — remove pedantic and add flutter_lints to dev_dependencies",
    "effective_dart": "Replaced by flutter_lints",
    "firebase_messaging_web": "Merged into firebase_messaging — remove this package",
}


def _parse_version(v: str) -> List[int]:
    """Parse a version string like '2.4.9' or '^2.4.9' into [2, 4, 9]."""
    v = v.strip().lstrip("^~>=<").split(" ")[0]
    parts = re.findall(r"\d+", v)
    return [int(p) for p in parts] if parts else [0]


def _version_lt(a: str, b: str) -> bool:
    """Returns True if version a < version b."""
    return _parse_version(a) < _parse_version(b)


def fix_all(project_root: str) -> List[FixResult]:
    results = []
    pubspec_path = os.path.join(project_root, "pubspec.yaml")
    if not os.path.exists(pubspec_path):
        return results

    with open(pubspec_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    original = content
    shutil.copy2(pubspec_path, pubspec_path + ".bak")

    results += _fix_deprecated(content, pubspec_path)
    results += _fix_outdated_versions(content, pubspec_path)
    results += _fix_dart3_compatibility(content, pubspec_path)
    results += _fix_dev_dep_in_deps(content, pubspec_path)

    return results


def _fix_deprecated(content: str, pubspec_path: str) -> List[FixResult]:
    results = []
    with open(pubspec_path, "r", encoding="utf-8", errors="ignore") as f:
        current = f.read()

    modified = current
    for pkg, suggestion in DEPRECATED_PACKAGES.items():
        if re.search(rf"^\s+{re.escape(pkg)}\s*:", current, re.MULTILINE):
            # Remove the line
            modified = re.sub(rf"^\s+{re.escape(pkg)}\s*:.*\n?", "", modified, flags=re.MULTILINE)
            results.append(FixResult(
                category=CATEGORY,
                issue=f"Deprecated package: {pkg}",
                fix=f"Removed {pkg}. {suggestion}",
                severity=Severity.MEDIUM,
                file_path="pubspec.yaml",
            ))

    if modified != current:
        with open(pubspec_path, "w", encoding="utf-8") as f:
            f.write(modified)
    return results


def _fix_outdated_versions(content: str, pubspec_path: str) -> List[FixResult]:
    results = []
    with open(pubspec_path, "r", encoding="utf-8", errors="ignore") as f:
        current = f.read()

    modified = current
    for pkg, (min_ver, recommended, reason) in KNOWN_VERSIONS.items():
        # Match: "  package_name: ^1.2.3" or "  package_name: 1.2.3"
        pattern = re.compile(rf"^(\s+{re.escape(pkg)}\s*:\s*)(\^?[\d.]+)", re.MULTILINE)
        match = pattern.search(current)
        if not match:
            continue
        current_ver = match.group(2).lstrip("^")
        if _version_lt(current_ver, min_ver):
            new_line = f"{match.group(1)}^{recommended}"
            modified = pattern.sub(new_line, modified, count=1)
            results.append(FixResult(
                category=CATEGORY,
                issue=f"{pkg}: version {current_ver} is too old (minimum {min_ver})",
                fix=f"Updated to ^{recommended}. Reason: {reason}",
                severity=Severity.HIGH,
                file_path="pubspec.yaml",
            ))

    if modified != current:
        with open(pubspec_path, "w", encoding="utf-8") as f:
            f.write(modified)
    return results


def _fix_dart3_compatibility(content: str, pubspec_path: str) -> List[FixResult]:
    """Ensure Dart SDK constraint supports Dart 3."""
    results = []
    with open(pubspec_path, "r", encoding="utf-8", errors="ignore") as f:
        current = f.read()

    # Look for SDK constraint that caps below Dart 3
    match = re.search(r"(sdk\s*:\s*['\"]?)([^'\"\n]+)(['\"]?)", current)
    if not match:
        return results

    constraint = match.group(2).strip()
    # Check upper bound
    upper = re.search(r"<(\d+)\.(\d+)", constraint)
    if upper and int(upper.group(1)) < 3:
        new_constraint = ">=3.0.0 <4.0.0"
        new_line = match.group(1) + new_constraint + match.group(3)
        modified = current[:match.start()] + new_line + current[match.end():]
        with open(pubspec_path, "w", encoding="utf-8") as f:
            f.write(modified)
        results.append(FixResult(
            category=CATEGORY,
            issue=f"SDK constraint '{constraint}' excludes Dart 3 — many modern packages require Dart 3",
            fix=f"Updated to '{new_constraint}'",
            severity=Severity.HIGH,
            file_path="pubspec.yaml",
        ))
    return results


def _fix_dev_dep_in_deps(content: str, pubspec_path: str) -> List[FixResult]:
    """Detect build-only packages accidentally placed in dependencies instead of dev_dependencies."""
    results = []
    build_only = {"build_runner", "hive_generator", "json_serializable", "freezed",
                  "retrofit_generator", "injectable_generator", "mockito", "bloc_test"}

    with open(pubspec_path, "r", encoding="utf-8", errors="ignore") as f:
        current = f.read()

    # Find the dependencies: block (not dev_dependencies)
    deps_match = re.search(r"^dependencies:\s*\n(.*?)(?=^dev_dependencies:|^flutter:|^environment:|^\S|\Z)",
                           current, re.MULTILINE | re.DOTALL)
    if not deps_match:
        return results

    deps_block = deps_match.group(1)
    wrongly_placed = []
    for pkg in build_only:
        if re.search(rf"^\s+{re.escape(pkg)}\s*:", deps_block, re.MULTILINE):
            wrongly_placed.append(pkg)

    if wrongly_placed:
        results.append(FixResult(
            category=CATEGORY,
            issue=f"Build-only packages in 'dependencies' instead of 'dev_dependencies': {', '.join(wrongly_placed)}",
            fix="Move these packages to dev_dependencies to avoid bloating your app bundle",
            severity=Severity.MEDIUM,
            file_path="pubspec.yaml",
            fixed=False,  # Safe to flag but risky to auto-move
        ))
    return results
