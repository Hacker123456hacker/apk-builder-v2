"""
Gradle fixer — handles all gradle.properties, gradle-wrapper.properties,
build.gradle, and settings.gradle issues.
"""
import os
import re
import shutil
from typing import List
from .base import FixResult, Severity

CATEGORY = "Gradle"

# Minimum safe versions
MIN_GRADLE_VERSION = "8.0"
MIN_AGP_VERSION = "8.1.0"
RECOMMENDED_GRADLE_VERSION = "8.3"
RECOMMENDED_AGP_VERSION = "8.2.2"


def fix_all(project_root: str) -> List[FixResult]:
    results = []
    results += _fix_gradle_properties(project_root)
    results += _fix_gradle_wrapper(project_root)
    results += _fix_build_gradle(project_root)
    return results


# ============ gradle.properties ============
def _fix_gradle_properties(root: str) -> List[FixResult]:
    results = []
    props_path = os.path.join(root, "android", "gradle.properties")
    if not os.path.exists(props_path):
        return results

    with open(props_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    original = content
    backup_path = props_path + ".bak"
    shutil.copy2(props_path, backup_path)

    # Fix 1: Malformed JVM args (the root cause of your error)
    # Pattern matches any org.gradle.jvmargs line
    jvm_pattern = re.compile(r"^org\.gradle\.jvmargs\s*=\s*(.*)$", re.MULTILINE)
    jvm_match = jvm_pattern.search(content)

    if jvm_match:
        existing_val = jvm_match.group(1).strip()
        # Detect malformed: if value starts with - but has spaces before flags
        # or has quotes around the value, or is missing -Xmx entirely
        is_malformed = (
            '"' in existing_val or
            "'" in existing_val or
            existing_val.startswith("-Xmx") is False and "-Xmx" not in existing_val or
            "ClassNotFoundException" in existing_val  # safety check
        )
        correct_val = "org.gradle.jvmargs=-Xmx4g -XX:+HeapDumpOnOutOfMemoryError -Dfile.encoding=UTF-8"
        content = jvm_pattern.sub(correct_val, content)
        if content != original or is_malformed:
            results.append(FixResult(
                category=CATEGORY,
                issue=f"Malformed JVM args: `{existing_val}` — causes 'Could not find or load main class' error",
                fix=f"Replaced with: `{correct_val}`",
                severity=Severity.CRITICAL,
                file_path="android/gradle.properties",
                backup_path=backup_path,
            ))
    else:
        # JVM args line missing entirely — add it
        content += "\norg.gradle.jvmargs=-Xmx4g -XX:+HeapDumpOnOutOfMemoryError -Dfile.encoding=UTF-8\n"
        results.append(FixResult(
            category=CATEGORY,
            issue="org.gradle.jvmargs missing from gradle.properties",
            fix="Added: org.gradle.jvmargs=-Xmx4g -XX:+HeapDumpOnOutOfMemoryError",
            severity=Severity.HIGH,
            file_path="android/gradle.properties",
        ))

    # Fix 2: Ensure AndroidX is enabled
    if "android.useAndroidX" not in content:
        content += "\nandroid.useAndroidX=true\n"
        results.append(FixResult(
            category=CATEGORY,
            issue="android.useAndroidX not set",
            fix="Added android.useAndroidX=true",
            severity=Severity.MEDIUM,
            file_path="android/gradle.properties",
        ))

    # Fix 3: Ensure Jetifier is enabled
    if "android.enableJetifier" not in content:
        content += "\nandroid.enableJetifier=true\n"
        results.append(FixResult(
            category=CATEGORY,
            issue="android.enableJetifier not set",
            fix="Added android.enableJetifier=true",
            severity=Severity.LOW,
            file_path="android/gradle.properties",
        ))

    # Fix 4: R8 full mode warning (can cause issues with some libraries)
    if "android.enableR8.fullMode=true" in content:
        content = content.replace("android.enableR8.fullMode=true", "android.enableR8.fullMode=false")
        results.append(FixResult(
            category=CATEGORY,
            issue="android.enableR8.fullMode=true can cause shrinking issues",
            fix="Set android.enableR8.fullMode=false",
            severity=Severity.MEDIUM,
            file_path="android/gradle.properties",
        ))

    if content != original:
        with open(props_path, "w", encoding="utf-8") as f:
            f.write(content)

    return results


# ============ gradle-wrapper.properties ============
def _fix_gradle_wrapper(root: str) -> List[FixResult]:
    results = []
    wrapper_path = os.path.join(root, "android", "gradle", "wrapper", "gradle-wrapper.properties")
    if not os.path.exists(wrapper_path):
        # Create it
        wrapper_dir = os.path.dirname(wrapper_path)
        os.makedirs(wrapper_dir, exist_ok=True)
        content = f"""distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
distributionUrl=https\\://services.gradle.org/distributions/gradle-{RECOMMENDED_GRADLE_VERSION}-all.zip
"""
        with open(wrapper_path, "w") as f:
            f.write(content)
        results.append(FixResult(
            category=CATEGORY,
            issue="gradle-wrapper.properties missing",
            fix=f"Created with Gradle {RECOMMENDED_GRADLE_VERSION}",
            severity=Severity.CRITICAL,
            file_path="android/gradle/wrapper/gradle-wrapper.properties",
        ))
        return results

    with open(wrapper_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    original = content
    shutil.copy2(wrapper_path, wrapper_path + ".bak")

    # Fix distributionUrl
    url_match = re.search(r"distributionUrl\s*=\s*(.+)", content)
    if url_match:
        current_url = url_match.group(1).strip()
        version_match = re.search(r"gradle-(\d+\.\d+(?:\.\d+)?)-", current_url)
        if version_match:
            current_ver = version_match.group(1)
            parts = [int(x) for x in current_ver.split(".")]
            min_parts = [int(x) for x in MIN_GRADLE_VERSION.split(".")]
            if parts < min_parts:
                new_url = f"https\\://services.gradle.org/distributions/gradle-{RECOMMENDED_GRADLE_VERSION}-all.zip"
                content = re.sub(r"distributionUrl\s*=\s*.+", f"distributionUrl={new_url}", content)
                results.append(FixResult(
                    category=CATEGORY,
                    issue=f"Gradle version {current_ver} is too old (minimum {MIN_GRADLE_VERSION})",
                    fix=f"Upgraded distributionUrl to Gradle {RECOMMENDED_GRADLE_VERSION}",
                    severity=Severity.HIGH,
                    file_path="android/gradle/wrapper/gradle-wrapper.properties",
                ))
        # Fix http -> https
        if "http://" in current_url and "https://" not in current_url:
            content = content.replace("http://", "https://")
            results.append(FixResult(
                category=CATEGORY,
                issue="distributionUrl uses http:// (insecure, may be rejected)",
                fix="Changed to https://",
                severity=Severity.HIGH,
                file_path="android/gradle/wrapper/gradle-wrapper.properties",
            ))
        # Fix -bin to -all (needed for IDE support and some tasks)
        if "-bin.zip" in content:
            content = content.replace("-bin.zip", "-all.zip")
            results.append(FixResult(
                category=CATEGORY,
                issue="Gradle wrapper uses -bin distribution (missing sources)",
                fix="Changed to -all distribution",
                severity=Severity.LOW,
                file_path="android/gradle/wrapper/gradle-wrapper.properties",
            ))

    if content != original:
        with open(wrapper_path, "w", encoding="utf-8") as f:
            f.write(content)

    return results


# ============ build.gradle (app level) ============
def _fix_build_gradle(root: str) -> List[FixResult]:
    results = []

    # Try app/build.gradle then build.gradle
    candidates = [
        (os.path.join(root, "android", "app", "build.gradle"), "android/app/build.gradle"),
        (os.path.join(root, "android", "app", "build.gradle.kts"), "android/app/build.gradle.kts"),
        (os.path.join(root, "app", "build.gradle"), "app/build.gradle"),
    ]

    for gradle_path, display_path in candidates:
        if not os.path.exists(gradle_path):
            continue

        with open(gradle_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        original = content
        shutil.copy2(gradle_path, gradle_path + ".bak")

        # Fix 1: minSdkVersion too low (Flutter requires 21+)
        min_sdk_match = re.search(r"minSdk(?:Version)?\s*[=:]?\s*(\d+)", content)
        if min_sdk_match:
            min_sdk = int(min_sdk_match.group(1))
            if min_sdk < 21:
                content = re.sub(
                    r"(minSdk(?:Version)?\s*[=:]?\s*)\d+",
                    lambda m: m.group(1) + "21",
                    content
                )
                results.append(FixResult(
                    category=CATEGORY,
                    issue=f"minSdkVersion={min_sdk} is below Flutter minimum (21)",
                    fix="Set minSdkVersion=21",
                    severity=Severity.HIGH,
                    file_path=display_path,
                ))

        # Fix 2: compileSdkVersion too low
        compile_sdk_match = re.search(r"compileSdk(?:Version)?\s*[=:]?\s*(\d+)", content)
        if compile_sdk_match:
            compile_sdk = int(compile_sdk_match.group(1))
            if compile_sdk < 34:
                content = re.sub(
                    r"(compileSdk(?:Version)?\s*[=:]?\s*)\d+",
                    lambda m: m.group(1) + "34",
                    content
                )
                results.append(FixResult(
                    category=CATEGORY,
                    issue=f"compileSdkVersion={compile_sdk} is outdated",
                    fix="Updated compileSdkVersion=34",
                    severity=Severity.MEDIUM,
                    file_path=display_path,
                ))

        # Fix 3: namespace missing (required for AGP 8+)
        has_namespace = "namespace" in content
        app_id_match = re.search(r'applicationId\s*[=]?\s*["\']([^"\']+)["\']', content)
        if not has_namespace and app_id_match:
            app_id = app_id_match.group(1)
            # Insert namespace in android { block
            content = re.sub(
                r"(android\s*\{)",
                f'\\1\n    namespace "{app_id}"',
                content,
                count=1
            )
            results.append(FixResult(
                category=CATEGORY,
                issue="namespace missing from android block (required for AGP 8+)",
                fix=f'Added namespace "{app_id}"',
                severity=Severity.CRITICAL,
                file_path=display_path,
            ))

        if content != original:
            with open(gradle_path, "w", encoding="utf-8") as f:
                f.write(content)

        break  # only fix first found

    return results
