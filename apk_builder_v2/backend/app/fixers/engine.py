"""
Fix Engine — orchestrates all fixers, runs them in order,
collects results, and re-packages the fixed project as a ZIP.
"""
import os
import shutil
import zipfile
import uuid
from typing import List, Tuple
from .base import AnalysisReport, FixResult
from . import gradle_fixer, flutter_fixer, android_fixer, workflow_fixer, dependency_fixer


def run_all_fixes(
    project_root: str,
    project_type: str,
    build_type: str,
) -> Tuple[AnalysisReport, str]:
    """
    Runs all fixers on the extracted project.
    Returns (AnalysisReport, workflow_yaml_string).
    """
    report = AnalysisReport(project_type=project_type, project_root=project_root)

    # Run fixers in order of importance
    if project_type in ("flutter", "android_native", "react_native"):
        # 1. Gradle fixes (most critical — your error was here)
        report.fix_results += gradle_fixer.fix_all(project_root)

    if project_type == "flutter":
        # 2. Flutter-specific fixes
        report.fix_results += flutter_fixer.fix_all(project_root)
        # 3. Dependency version fixes
        report.fix_results += dependency_fixer.fix_all(project_root)

    # 3. Android manifest fixes (all project types)
    report.fix_results += android_fixer.fix_all(project_root)

    # 4. Generate fixed workflow YAML
    workflow_yaml, workflow_fixes = workflow_fixer.generate_and_fix(project_root, project_type, build_type)
    report.fix_results += workflow_fixes

    return report, workflow_yaml


def package_fixed_zip(project_root: str, output_dir: str, original_name: str) -> str:
    """
    Re-zips the (now fixed) project directory into a downloadable ZIP.
    Returns the absolute path to the ZIP file.
    """
    os.makedirs(output_dir, exist_ok=True)
    zip_filename = f"fixed_{original_name}_{uuid.uuid4().hex[:8]}.zip"
    zip_path = os.path.join(output_dir, zip_filename)

    # Excludes: don't re-include backup files or __pycache__
    exclude_suffixes = (".bak", ".pyc")
    exclude_dirs = {"__pycache__", ".git", "build", "node_modules", ".dart_tool"}

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(project_root):
            dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
            for fname in filenames:
                if any(fname.endswith(s) for s in exclude_suffixes):
                    continue
                abs_path = os.path.join(dirpath, fname)
                arcname = os.path.relpath(abs_path, project_root)
                zf.write(abs_path, arcname)

    return zip_path
