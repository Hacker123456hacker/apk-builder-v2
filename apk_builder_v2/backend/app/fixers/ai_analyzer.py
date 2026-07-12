"""
AI Error Analyzer — parses raw GitHub Actions build logs and produces
structured error summaries and actionable suggestions.
No external LLM API required — this is rule-based pattern matching
covering the most common Flutter/Gradle/Android build errors.
"""
import re
from typing import List, Tuple


# Each entry: (regex_pattern, category, summary, suggestion)
ERROR_PATTERNS: List[Tuple[str, str, str, str]] = [
    # Gradle JVM args
    (
        r"Could not find or load main class.*-Xmx",
        "Gradle",
        "Malformed JVM arguments in gradle.properties",
        "The org.gradle.jvmargs line has invalid formatting. The fix step in the workflow should have corrected this — try rebuilding. If it persists, manually set: org.gradle.jvmargs=-Xmx4g"
    ),
    # Namespace missing
    (
        r"Namespace not specified",
        "Android",
        "Missing namespace in build.gradle",
        "AGP 8+ requires a namespace declaration in app/build.gradle. Add: namespace 'com.your.package.name' inside the android { } block."
    ),
    # SDK version
    (
        r"uses-sdk:minSdkVersion (\d+) cannot be smaller than version (\d+)",
        "Android",
        "minSdkVersion conflict with a dependency",
        "A dependency requires a higher minSdkVersion than your app. Set minSdkVersion to at least the required value in app/build.gradle."
    ),
    # Flutter pub get failure
    (
        r"Because .+ depends on .+ which doesn't match",
        "Flutter",
        "Dependency version conflict in pubspec.yaml",
        "Two or more packages require incompatible versions of a dependency. Run `flutter pub deps` locally to identify the conflict, then pin a compatible version."
    ),
    # Kotlin version
    (
        r"Kotlin version (\S+) is below the minimum required version",
        "Flutter",
        "Kotlin version too old for current Flutter/AGP",
        "Update ext.kotlin_version in android/build.gradle to 1.9.22 or higher."
    ),
    # Java version
    (
        r"Unsupported class file major version",
        "Gradle",
        "Java version mismatch — compiled with a newer JDK than the runner supports",
        "Ensure the workflow uses Java 17 (actions/setup-java with java-version: '17'). The workflow should already have this — check if a local gradle.properties is overriding the JDK."
    ),
    # Missing main.dart
    (
        r"Target of URI doesn't exist.*main\.dart",
        "Flutter",
        "lib/main.dart not found",
        "The Flutter entry point lib/main.dart is missing from the uploaded ZIP. Make sure the ZIP includes the full lib/ directory."
    ),
    # Hive missing adapter
    (
        r"Error.*TypeAdapter.*not found|HiveError.*TypeAdapter",
        "Hive",
        "Hive TypeAdapter not registered or not generated",
        "Run `dart run build_runner build --delete-conflicting-outputs` to generate .g.dart files. The workflow should do this automatically — verify the 'Generate code' step ran successfully."
    ),
    # Out of memory
    (
        r"OutOfMemoryError|GC overhead limit exceeded|Java heap space",
        "Gradle",
        "Build ran out of memory",
        "Increase Gradle heap: set org.gradle.jvmargs=-Xmx6g in gradle.properties. GitHub Actions runners have 7GB RAM available."
    ),
    # license not accepted
    (
        r"Android SDK license|licenses? not accepted",
        "Android",
        "Android SDK license not accepted",
        "Add a step to the workflow: `echo y | $ANDROID_SDK_ROOT/cmdline-tools/latest/bin/sdkmanager --licenses`"
    ),
    # NDK
    (
        r"NDK at .+ is missing a required components",
        "Android",
        "NDK version issue",
        "Specify the NDK version in app/build.gradle: android { ndkVersion '25.1.8937393' }"
    ),
    # Gradle build failure generic
    (
        r"BUILD FAILED",
        "Gradle",
        "Gradle build failed",
        "Scroll up in the log to find the specific error above 'BUILD FAILED'. The actual cause is always listed earlier in the output."
    ),
    # Execution failed
    (
        r"Execution failed for task ':app:compile",
        "Flutter",
        "Dart/Flutter compilation error",
        "There is a Dart code error in your project. Check the log lines immediately above this error for the specific file and line number."
    ),
]


def analyze_log(log_text: str) -> dict:
    """
    Parses a raw build log and returns:
    {
        'summary': str,
        'matched_errors': [{'category', 'summary', 'suggestion', 'matched_line'}],
        'relevant_lines': [str],  # most important log lines
        'overall_category': str,
    }
    """
    if not log_text:
        return {"summary": "No log available.", "matched_errors": [], "relevant_lines": [], "overall_category": "Unknown"}

    lines = log_text.split("\n")
    matched_errors = []
    seen_summaries = set()

    for line in lines:
        for pattern, category, summary, suggestion in ERROR_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE) and summary not in seen_summaries:
                matched_errors.append({
                    "category": category,
                    "summary": summary,
                    "suggestion": suggestion,
                    "matched_line": line.strip()[:200],
                })
                seen_summaries.add(summary)

    # Extract relevant lines: error/exception/failure lines
    relevant_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        low = stripped.lower()
        if any(kw in low for kw in ["error:", "exception:", "failed", "failure", "cannot", "could not", "not found", "missing"]):
            # Skip very long lines (stack traces etc)
            if len(stripped) < 300:
                relevant_lines.append(stripped)
        if len(relevant_lines) >= 25:
            break

    # Determine overall category
    if matched_errors:
        categories = [e["category"] for e in matched_errors]
        overall_category = max(set(categories), key=categories.count)
    else:
        overall_category = "Unknown"

    if matched_errors:
        primary = matched_errors[0]
        summary = f"{primary['category']} Error: {primary['summary']}"
    elif relevant_lines:
        summary = f"Build failed. First error: {relevant_lines[0][:150]}"
    else:
        summary = "Build failed — check the full log on GitHub for details."

    return {
        "summary": summary,
        "matched_errors": matched_errors,
        "relevant_lines": relevant_lines,
        "overall_category": overall_category,
    }
