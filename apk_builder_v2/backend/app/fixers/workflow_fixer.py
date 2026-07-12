"""
Workflow fixer — generates a robust GitHub Actions workflow YAML
with all known fixes baked in (JVM args repair, build_runner support,
Hive adapter generation, Flutter create fallback, etc.)
"""
import os
import re
from typing import List
from .base import FixResult, Severity

CATEGORY = "GitHub Actions"
WORKFLOW_FILE_NAME = "ai-apk-builder.yml"
WORKFLOW_PATH = f".github/workflows/{WORKFLOW_FILE_NAME}"


def generate_and_fix(project_root: str, project_type: str, build_type: str) -> tuple[str, List[FixResult]]:
    """
    Returns (workflow_yaml_string, list_of_fix_results).
    Inspects the project to decide which extra steps are needed.
    """
    results = []
    needs_build_runner = _needs_build_runner(project_root)
    has_gradlew = _has_gradlew(project_root)

    if needs_build_runner:
        results.append(FixResult(
            category=CATEGORY,
            issue="Project uses code generation (Hive/json_serializable/freezed) — build_runner must run before building",
            fix="Added `dart run build_runner build --delete-conflicting-outputs` step to workflow",
            severity=Severity.CRITICAL,
            file_path=WORKFLOW_PATH,
        ))

    if not has_gradlew and project_type in ("android_native", "react_native"):
        results.append(FixResult(
            category=CATEGORY,
            issue="gradlew wrapper script missing",
            fix="Workflow will generate the Gradle wrapper before building",
            severity=Severity.HIGH,
            file_path=WORKFLOW_PATH,
        ))

    if project_type == "flutter":
        yaml = _flutter_workflow(build_type, needs_build_runner)
    elif project_type == "android_native":
        yaml = _android_native_workflow(build_type, has_gradlew)
    elif project_type == "react_native":
        yaml = _react_native_workflow(build_type)
    else:
        yaml = _flutter_workflow(build_type, needs_build_runner)

    return yaml, results


def _needs_build_runner(root: str) -> bool:
    pubspec = os.path.join(root, "pubspec.yaml")
    if not os.path.exists(pubspec):
        return False
    with open(pubspec, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    triggers = ["hive_generator", "json_serializable", "freezed", "retrofit_generator", "build_runner"]
    return any(t in content for t in triggers)


def _has_gradlew(root: str) -> bool:
    return (
        os.path.exists(os.path.join(root, "android", "gradlew")) or
        os.path.exists(os.path.join(root, "gradlew"))
    )


def _flutter_workflow(build_type: str, needs_build_runner: bool) -> str:
    build_cmd = "flutter build appbundle --release" if build_type == "aab" else "flutter build apk --release"
    output_path = (
        "build/app/outputs/bundle/release/app-release.aab"
        if build_type == "aab"
        else "build/app/outputs/flutter-apk/app-release.apk"
    )

    build_runner_step = """
      - name: Generate code (build_runner)
        run: dart run build_runner build --delete-conflicting-outputs
""" if needs_build_runner else ""

    return f"""name: AI APK Builder - Flutter Build

on:
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: 'zulu'
          java-version: '17'

      - name: Set up Flutter
        uses: subosito/flutter-action@v2
        with:
          channel: 'stable'

      - name: Create Android project if missing
        run: |
          if [ ! -d "android" ]; then
            echo "android/ not found — running flutter create"
            flutter create --platforms=android .
          fi

      - name: Fix gradle.properties JVM args
        run: |
          PROPS="android/gradle.properties"
          # Remove any existing jvmargs line (handles malformed ones)
          sed -i '/^org\\.gradle\\.jvmargs/d' "$PROPS" 2>/dev/null || true
          # Write a clean correct line
          echo 'org.gradle.jvmargs=-Xmx4g -XX:+HeapDumpOnOutOfMemoryError -Dfile.encoding=UTF-8' >> "$PROPS"
          echo 'android.useAndroidX=true' >> "$PROPS"
          echo 'android.enableJetifier=true' >> "$PROPS"
          echo "--- gradle.properties ---"
          cat "$PROPS"

      - name: Get dependencies
        run: flutter pub get
{build_runner_step}
      - name: Build {build_type}
        run: {build_cmd}

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: app-{build_type}-release
          path: {output_path}
          retention-days: 14
"""


def _android_native_workflow(build_type: str, has_gradlew: bool) -> str:
    gradle_task = "bundleRelease" if build_type == "aab" else "assembleRelease"
    output_glob = (
        "app/build/outputs/bundle/release/*.aab"
        if build_type == "aab"
        else "app/build/outputs/apk/release/*.apk"
    )
    gradlew_setup = """
      - name: Ensure gradlew exists
        run: |
          if [ ! -f "./gradlew" ]; then
            gradle wrapper --gradle-version 8.3
          fi
          chmod +x ./gradlew
""" if not has_gradlew else """
      - name: Make gradlew executable
        run: chmod +x ./gradlew
"""

    return f"""name: AI APK Builder - Android Native Build

on:
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: 'zulu'
          java-version: '17'
{gradlew_setup}
      - name: Fix gradle.properties JVM args
        run: |
          PROPS="gradle.properties"
          if [ ! -f "$PROPS" ]; then PROPS="app/gradle.properties"; fi
          sed -i '/^org\\.gradle\\.jvmargs/d' "$PROPS" 2>/dev/null || true
          echo 'org.gradle.jvmargs=-Xmx4g -XX:+HeapDumpOnOutOfMemoryError' >> "$PROPS"

      - name: Build {build_type}
        run: ./gradlew {gradle_task} --no-daemon

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: app-{build_type}-release
          path: {output_glob}
          retention-days: 14
"""


def _react_native_workflow(build_type: str) -> str:
    gradle_task = "bundleRelease" if build_type == "aab" else "assembleRelease"
    output_glob = (
        "android/app/build/outputs/bundle/release/*.aab"
        if build_type == "aab"
        else "android/app/build/outputs/apk/release/*.apk"
    )

    return f"""name: AI APK Builder - React Native Build

on:
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: 'zulu'
          java-version: '17'

      - name: Install JS dependencies
        run: npm install

      - name: Fix gradle.properties JVM args
        run: |
          PROPS="android/gradle.properties"
          sed -i '/^org\\.gradle\\.jvmargs/d' "$PROPS" 2>/dev/null || true
          echo 'org.gradle.jvmargs=-Xmx4g -XX:+HeapDumpOnOutOfMemoryError' >> "$PROPS"

      - name: Make gradlew executable
        run: chmod +x android/gradlew

      - name: Build {build_type}
        run: cd android && ./gradlew {gradle_task} --no-daemon

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: app-{build_type}-release
          path: {output_glob}
          retention-days: 14
"""
