"""
Auto-Fix Engine — data structures and base fixer interface.
Each fixer is responsible for one category of issues.
"""
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "critical"   # build will definitely fail
    HIGH = "high"           # build will likely fail
    MEDIUM = "medium"       # build may fail or behave unexpectedly
    LOW = "low"             # best practice / warning


@dataclass
class FixResult:
    category: str           # e.g. "Gradle", "Flutter", "Android"
    issue: str              # human-readable description of what was wrong
    fix: str                # what was done to fix it
    severity: Severity
    file_path: str          # which file was modified
    fixed: bool = True      # False if issue was detected but could not be auto-fixed
    backup_path: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "issue": self.issue,
            "fix": self.fix,
            "severity": self.severity.value,
            "file_path": self.file_path,
            "fixed": self.fixed,
        }


@dataclass
class AnalysisReport:
    project_type: str
    project_root: str
    fix_results: List[FixResult] = field(default_factory=list)
    unfixed_issues: List[FixResult] = field(default_factory=list)

    @property
    def total_issues(self) -> int:
        return len(self.fix_results) + len(self.unfixed_issues)

    @property
    def total_fixed(self) -> int:
        return sum(1 for r in self.fix_results if r.fixed)

    @property
    def critical_count(self) -> int:
        all_issues = self.fix_results + self.unfixed_issues
        return sum(1 for r in all_issues if r.severity == Severity.CRITICAL)

    def all_results(self) -> List[FixResult]:
        return self.fix_results + self.unfixed_issues

    def to_dict_list(self) -> List[dict]:
        return [r.to_dict() for r in self.all_results()]
