import os, re, shutil, zipfile, uuid, asyncio
from datetime import datetime
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session as DBSession

from ..database import get_db, Session as SessionModel, BuildJob
from ..session import get_current_session, get_optional_session, get_decrypted_token
from ..services.github_service import GitHubService, GitHubAPIError
from ..services.project_analyzer import ProjectAnalyzer, PROJECT_TYPE_LABELS, PROJECT_TYPE_ICONS
from ..services.file_collector import FileCollector
from ..fixers.engine import run_all_fixes, package_fixed_zip
from ..fixers.workflow_fixer import WORKFLOW_FILE_NAME, WORKFLOW_PATH
from ..fixers.ai_analyzer import analyze_log
from ..fixers.report_generator import generate_html_report, generate_json_report
from ..job_registry import registry

router = APIRouter(prefix="/api/build", tags=["build"])

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
EXTRACTED_DIR = os.path.join(DATA_DIR, "extracted")
DOWNLOADS_DIR = os.path.join(DATA_DIR, "downloads")
FIXED_ZIPS_DIR = os.path.join(DATA_DIR, "fixed_zips")
REPORTS_DIR = os.path.join(DATA_DIR, "reports")
for d in (UPLOADS_DIR, EXTRACTED_DIR, DOWNLOADS_DIR, FIXED_ZIPS_DIR, REPORTS_DIR):
    os.makedirs(d, exist_ok=True)

MAX_RETRIES = 3  # max build-fix-rebuild cycles


def _sanitize(name: str) -> str:
    clean = name.lower().strip()
    clean = re.sub(r"[^a-z0-9\-_]", "-", clean)
    clean = re.sub(r"-+", "-", clean)
    return clean or "app"


# ============ STEP 1: ANALYZE + AUTO-FIX ============
@router.post("/analyze")
async def analyze_zip(file: UploadFile = File(...), session: SessionModel = Depends(get_current_session)):
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Please upload a .zip file.")

    analysis_id = str(uuid.uuid4())
    zip_path = os.path.join(UPLOADS_DIR, f"{analysis_id}.zip")
    extract_path = os.path.join(EXTRACTED_DIR, analysis_id)

    content = await file.read()
    with open(zip_path, "wb") as f:
        f.write(content)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.namelist():
                target = os.path.normpath(os.path.join(extract_path, member))
                if not target.startswith(os.path.normpath(extract_path)):
                    raise HTTPException(status_code=400, detail="Unsafe path in ZIP.")
            zf.extractall(extract_path)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Could not read ZIP — may be corrupted.")

    project_root = ProjectAnalyzer.resolve_project_root(extract_path)
    result = ProjectAnalyzer.analyze(project_root)
    original_name = os.path.splitext(file.filename)[0]
    suggested_name = _sanitize(result["detected_info"].get("package_name", original_name))

    return {
        "analysis_id": analysis_id,
        "original_filename": file.filename,
        "type": result["type"],
        "type_label": PROJECT_TYPE_LABELS[result["type"]],
        "type_icon": PROJECT_TYPE_ICONS[result["type"]],
        "is_valid": result["is_valid"],
        "errors": result["errors"],
        "warnings": result["warnings"],
        "detected_info": result["detected_info"],
        "suggested_repo_name": suggested_name,
    }


# ============ STEP 2: RUN AUTO-FIX + GET FIXED ZIP ============
@router.post("/fix/{analysis_id}")
async def run_fix(
    analysis_id: str,
    build_type: str = Form("apk"),
    session: SessionModel = Depends(get_current_session),
):
    extract_path = os.path.join(EXTRACTED_DIR, analysis_id)
    if not os.path.exists(extract_path):
        raise HTTPException(status_code=404, detail="Analysis not found or expired.")

    project_root = ProjectAnalyzer.resolve_project_root(extract_path)
    result = ProjectAnalyzer.analyze(project_root)

    report, _ = run_all_fixes(project_root, result["type"], build_type)

    fix_dicts = [r.to_dict() for r in report.all_results()]

    return {
        "analysis_id": analysis_id,
        "total_issues": report.total_issues,
        "total_fixed": report.total_fixed,
        "critical_count": report.critical_count,
        "fix_results": fix_dicts,
        "ready_to_build": True,
    }


# ============ STEP 2b: DOWNLOAD FIXED ZIP ============
@router.get("/download-fixed/{analysis_id}")
async def download_fixed_zip(analysis_id: str, session: SessionModel = Depends(get_current_session)):
    extract_path = os.path.join(EXTRACTED_DIR, analysis_id)
    if not os.path.exists(extract_path):
        raise HTTPException(status_code=404, detail="Analysis not found or expired.")

    project_root = ProjectAnalyzer.resolve_project_root(extract_path)
    result = ProjectAnalyzer.analyze(project_root)

    # Re-run fixes to ensure they are applied (idempotent)
    run_all_fixes(project_root, result["type"], "apk")

    original_name = os.path.basename(project_root)
    zip_path = package_fixed_zip(project_root, FIXED_ZIPS_DIR, original_name)
    return FileResponse(zip_path, filename=os.path.basename(zip_path), media_type="application/zip")


# ============ STEP 3: START CLOUD BUILD ============
@router.post("/start")
async def start_build(
    background_tasks: BackgroundTasks,
    analysis_id: str = Form(...),
    repo_name: str = Form(...),
    build_type: str = Form("apk"),
    session: SessionModel = Depends(get_current_session),
    db: DBSession = Depends(get_db),
):
    extract_path = os.path.join(EXTRACTED_DIR, analysis_id)
    if not os.path.exists(extract_path):
        raise HTTPException(status_code=404, detail="Analysis expired. Please re-upload.")

    project_root = ProjectAnalyzer.resolve_project_root(extract_path)
    result = ProjectAnalyzer.analyze(project_root)

    repo_name = _sanitize(repo_name)
    build_id = str(uuid.uuid4())
    token = get_decrypted_token(session)

    db.add(BuildJob(
        id=build_id, session_id=session.id,
        project_name=repo_name,
        project_type=PROJECT_TYPE_LABELS[result["type"]],
        repo_full_name=f"{session.github_login}/{repo_name}",
        build_type=build_type, phase="fixing",
        started_at=datetime.utcnow(),
    ))
    db.commit()

    job = await registry.create(build_id)
    job.owner = session.github_login
    job.repo = repo_name

    background_tasks.add_task(
        _pipeline, build_id=build_id, token=token, owner=session.github_login,
        repo_name=repo_name, project_root=project_root,
        project_type=result["type"], build_type=build_type,
    )
    return {"build_id": build_id}


async def _pipeline(build_id, token, owner, repo_name, project_root, project_type, build_type):
    job = registry.get(build_id)
    github = GitHubService(token)
    db = next(get_db())

    def save(**kwargs):
        h = db.query(BuildJob).filter(BuildJob.id == build_id).first()
        if h:
            for k, v in kwargs.items(): setattr(h, k, v)
            db.commit()

    all_fix_results = []
    retry_count = 0
    last_ai_analysis = None

    try:
        # ============ RETRY LOOP ============
        while retry_count < MAX_RETRIES:
            attempt = retry_count + 1
            if retry_count > 0:
                job.log(f"")
                job.log(f"🔁 ── RETRY ATTEMPT {attempt}/{MAX_RETRIES} ──────────────────")
                job.log(f"Applying additional fixes based on previous failure...")

            # ── PHASE: Auto-fix ──
            job.phase = "fixing"
            job.log(f"🔧 Running Auto-Fix Engine (attempt {attempt})...")
            report, workflow_yaml = run_all_fixes(project_root, project_type, build_type)

            # On retry: also apply AI-suggested fixes if we have them
            if retry_count > 0 and last_ai_analysis:
                _apply_ai_suggested_fixes(project_root, last_ai_analysis, job)

            all_fix_results += report.all_results()
            job.fix_results = [r.to_dict() for r in all_fix_results]
            job.issues_found = len(all_fix_results)
            job.issues_fixed = sum(1 for r in all_fix_results if r.fixed)
            save(phase="fixing", issues_found=job.issues_found,
                 issues_fixed=job.issues_fixed, fix_log=job.fix_results)

            new_fixes = report.all_results()
            if new_fixes:
                for r in new_fixes:
                    icon = "✓" if r.fixed else "⚠"
                    job.log(f"  {icon} [{r.category}] {r.issue}")
                job.log(f"🔧 Fixed {report.total_fixed}/{report.total_issues} issues this pass")
            else:
                job.log("  No new fixable issues found")

            # ── PHASE: Upload ──
            job.phase = "uploading"
            job.log(f"📁 Pushing to {owner}/{repo_name}...")
            repo = await github.get_or_create_repo(owner, repo_name)
            branch = repo["default_branch"]

            files = FileCollector.collect(project_root)
            count, total = FileCollector.summarize(files)
            job.log(f"📤 Uploading {count} files ({FileCollector.format_bytes(total)}) as a single commit...")

            workflow_bytes = workflow_yaml.encode("utf-8")
            files_to_push = {path: open(disk_path, "rb").read() for path, disk_path in files.items()}
            files_to_push[WORKFLOW_PATH] = workflow_bytes
            total_files = len(files_to_push)

            def _on_progress(done, total_n, path, _job=job):
                _job.upload_progress = done / total_n
                _job.upload_label = f"{done}/{total_n} — {path}"

            await github.push_files(
                owner, repo_name, branch, files_to_push,
                message=f"Auto-fix build {build_id} (attempt {attempt})",
                progress_cb=_on_progress,
            )

            job.log(f"✓ Uploaded {total_files} files in a single commit")
            save(phase="building")

            # ── PHASE: Trigger ──
            job.phase = "building"
            job.log("🚀 Triggering GitHub Actions...")
            await asyncio.sleep(3)
            await github.trigger_workflow(owner, repo_name, WORKFLOW_FILE_NAME, branch)
            job.log("✓ Workflow triggered")

            run = None
            for _ in range(12):
                await asyncio.sleep(2)
                run = await github.find_latest_run(owner, repo_name, WORKFLOW_FILE_NAME)
                if run: break

            if not run:
                job.phase = "error"; job.error = "Run not found after trigger."
                save(phase="error", status="error", finished_at=datetime.utcnow())
                break

            job.run_id = run["id"]; job.html_url = run["html_url"]
            job.status = _map(run)
            job.log(f"▶ Run #{run['id']} — {run['html_url']}")
            save(run_id=str(run["id"]), html_url=run["html_url"])

            # ── PHASE: Poll ──
            build_succeeded = False
            while True:
                await asyncio.sleep(8)
                run = await github.get_run(owner, repo_name, run["id"])
                if not run: continue
                jobs_list = await github.get_run_jobs(owner, repo_name, run["id"])
                job.steps = jobs_list[0]["steps"] if jobs_list else []
                job.status = _map(run)

                if run["status"] == "completed":
                    if run["conclusion"] == "success":
                        job.log("✅ Build succeeded!")
                        job.phase = "done"
                        build_succeeded = True
                        artifacts = await github.get_artifacts(owner, repo_name, run["id"])
                        job.artifacts = artifacts
                        save(phase="done", status="succeeded", finished_at=datetime.utcnow(),
                             artifact_download_url=artifacts[0]["archive_download_url"] if artifacts else None,
                             artifact_name=artifacts[0]["name"] if artifacts else None,
                             artifact_size_bytes=artifacts[0]["size_in_bytes"] if artifacts else None)
                    else:
                        job.log(f"❌ Build failed (attempt {attempt}/{MAX_RETRIES})")
                        raw_log = None
                        if jobs_list:
                            raw_log = await github.get_job_logs(owner, repo_name, jobs_list[0]["id"])
                        if raw_log:
                            ai = analyze_log(raw_log)
                            last_ai_analysis = ai
                            job.ai_analysis = ai
                            job.log(f"🤖 AI: {ai['summary']}")
                            for e in ai["matched_errors"]:
                                job.log(f"  [{e['category']}] {e['summary']}")
                                job.log(f"  → {e['suggestion']}")
                            tail = [l for l in raw_log.split("\n") if l.strip()][-30:]
                            for line in tail: job.log(line)
                            save(log_summary="\n".join(tail),
                                 ai_error_summary=ai["summary"],
                                 ai_suggestions=ai["matched_errors"])
                    break

            if build_succeeded:
                break

            retry_count += 1
            if retry_count >= MAX_RETRIES:
                job.log(f"⛔ Max retries ({MAX_RETRIES}) reached. Build could not be fixed automatically.")
                status_val = {"failure": "failed", "cancelled": "cancelled"}.get(
                    run.get("conclusion", ""), "error")
                save(phase="error", status=status_val, finished_at=datetime.utcnow())
                break

            job.log(f"⏳ Waiting 5s before retry...")
            await asyncio.sleep(5)

        # ── Generate fix report ──
        _save_report(build_id, repo_name, project_type, job, all_fix_results, last_ai_analysis)

    except GitHubAPIError as e:
        job.phase = "error"; job.error = str(e); job.log(f"❌ GitHub error: {e}")
        save(phase="error", status="error", finished_at=datetime.utcnow())
    except Exception as e:
        job.phase = "error"; job.error = str(e); job.log(f"❌ Error: {e}")
        save(phase="error", status="error", finished_at=datetime.utcnow())
    finally:
        db.close()


def _apply_ai_suggested_fixes(project_root: str, ai_analysis: dict, job):
    """Apply targeted fixes based on AI-identified error patterns."""
    from ..fixers.gradle_fixer import fix_all as gradle_fix_all
    from ..fixers.android_fixer import fix_all as android_fix_all

    for err in ai_analysis.get("matched_errors", []):
        category = err.get("category", "")
        summary = err.get("summary", "")

        if category == "Gradle" and "JVM" in summary:
            results = gradle_fix_all(project_root)
            for r in results:
                job.log(f"  🔧 AI-guided fix: {r.fix}")

        if category == "Android" and "namespace" in summary.lower():
            results = android_fix_all(project_root)
            for r in results:
                job.log(f"  🔧 AI-guided fix: {r.fix}")

        if category == "Gradle" and "memory" in summary.lower():
            # Increase JVM heap further
            props_path = os.path.join(project_root, "android", "gradle.properties")
            if os.path.exists(props_path):
                import re
                with open(props_path, "r") as f:
                    content = f.read()
                content = re.sub(r"org\.gradle\.jvmargs=.*",
                                  "org.gradle.jvmargs=-Xmx6g -XX:+HeapDumpOnOutOfMemoryError",
                                  content)
                with open(props_path, "w") as f:
                    f.write(content)
                job.log("  🔧 AI-guided: Increased Gradle heap to 6GB")


def _save_report(build_id, project_name, project_type, job, all_fix_results, ai_analysis):
    """Save HTML and JSON fix reports to disk."""
    try:
        from ..fixers.base import FixResult
        html = generate_html_report(
            project_name=project_name,
            project_type=project_type,
            build_status=job.status,
            fix_results=all_fix_results,
            ai_analysis=ai_analysis,
            build_url=job.html_url,
        )
        json_str = generate_json_report(
            project_name=project_name,
            project_type=project_type,
            build_status=job.status,
            fix_results=all_fix_results,
            ai_analysis=ai_analysis,
        )
        with open(os.path.join(REPORTS_DIR, f"{build_id}.html"), "w") as f:
            f.write(html)
        with open(os.path.join(REPORTS_DIR, f"{build_id}.json"), "w") as f:
            f.write(json_str)
    except Exception as e:
        pass  # Don't let report generation failure break the build


def _map(run: dict) -> str:
    if run["status"] == "queued": return "queued"
    if run["status"] == "in_progress": return "running"
    return {"success": "succeeded", "failure": "failed", "cancelled": "cancelled"}.get(run.get("conclusion", ""), "error")


# ============ STATUS ============
@router.get("/status/{build_id}")
async def get_status(build_id: str, session=Depends(get_current_session)):
    job = registry.get(build_id)
    if job:
        return {
            "phase": job.phase, "status": job.status, "html_url": job.html_url,
            "steps": job.steps, "log_lines": job.log_lines,
            "upload_progress": job.upload_progress, "upload_label": job.upload_label,
            "artifacts": job.artifacts, "error": job.error,
            "fix_results": job.fix_results, "issues_found": job.issues_found,
            "issues_fixed": job.issues_fixed, "ai_analysis": job.ai_analysis,
        }
    db = next(get_db())
    h = db.query(BuildJob).filter(BuildJob.id == build_id).first()
    db.close()
    if not h: raise HTTPException(status_code=404, detail="Build not found.")
    return {
        "phase": h.phase, "status": h.status, "html_url": h.html_url,
        "steps": [], "log_lines": [h.log_summary] if h.log_summary else [],
        "upload_progress": 1.0, "upload_label": None,
        "artifacts": [{"name": h.artifact_name, "size_in_bytes": h.artifact_size_bytes,
                        "archive_download_url": h.artifact_download_url}] if h.artifact_download_url else [],
        "error": None, "fix_results": h.fix_log or [], "issues_found": h.issues_found,
        "issues_fixed": h.issues_fixed,
        "ai_analysis": {"summary": h.ai_error_summary, "matched_errors": h.ai_suggestions or []} if h.ai_error_summary else None,
    }


# ============ DOWNLOAD APK ============
@router.get("/download/{build_id}")
async def download_apk(build_id: str, session=Depends(get_current_session), db: DBSession = Depends(get_db)):
    h = db.query(BuildJob).filter(BuildJob.id == build_id).first()
    if not h or not h.artifact_download_url:
        raise HTTPException(status_code=404, detail="No artifact available.")
    token = get_decrypted_token(session)
    zip_bytes = await GitHubService(token).download_artifact(h.artifact_download_url)
    if not zip_bytes: raise HTTPException(status_code=502, detail="Download from GitHub failed.")

    tmp = os.path.join(DOWNLOADS_DIR, f"{build_id}_art.zip")
    with open(tmp, "wb") as f: f.write(zip_bytes)
    output_path = None
    with zipfile.ZipFile(tmp, "r") as zf:
        for name in zf.namelist():
            if name.endswith(".apk") or name.endswith(".aab"):
                out = os.path.join(DOWNLOADS_DIR, f"{build_id}_{os.path.basename(name)}")
                with zf.open(name) as src, open(out, "wb") as dst:
                    import shutil; shutil.copyfileobj(src, dst)
                output_path = out; break
    os.remove(tmp)
    if not output_path: raise HTTPException(status_code=404, detail="No APK/AAB in artifact.")
    filename = os.path.basename(output_path).split("_", 1)[-1]
    return FileResponse(output_path, filename=filename, media_type="application/octet-stream")


# ============ HISTORY ============
@router.get("/history")
async def history(session=Depends(get_current_session), db: DBSession = Depends(get_db)):
    items = db.query(BuildJob).filter(BuildJob.session_id == session.id).order_by(BuildJob.started_at.desc()).all()
    return [{
        "id": h.id, "project_name": h.project_name, "project_type": h.project_type,
        "repo_full_name": h.repo_full_name, "build_type": h.build_type,
        "phase": h.phase, "status": h.status, "html_url": h.html_url,
        "has_artifact": bool(h.artifact_download_url),
        "issues_found": h.issues_found, "issues_fixed": h.issues_fixed,
        "started_at": h.started_at.isoformat() if h.started_at else None,
        "finished_at": h.finished_at.isoformat() if h.finished_at else None,
    } for h in items]


@router.delete("/history/{build_id}")
async def del_history(build_id: str, session=Depends(get_current_session), db: DBSession = Depends(get_db)):
    db.query(BuildJob).filter(BuildJob.id == build_id, BuildJob.session_id == session.id).delete()
    db.commit(); registry.remove(build_id)
    return {"success": True}


@router.delete("/history")
async def clear_history(session=Depends(get_current_session), db: DBSession = Depends(get_db)):
    db.query(BuildJob).filter(BuildJob.session_id == session.id).delete()
    db.commit(); return {"success": True}


# ============ FIX REPORTS ============
@router.get("/report/{build_id}/html")
async def download_html_report(build_id: str, session=Depends(get_current_session)):
    path = os.path.join(REPORTS_DIR, f"{build_id}.html")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Report not yet generated. Complete a build first.")
    with open(path, "r") as f:
        content = f.read()
    return HTMLResponse(content=content)


@router.get("/report/{build_id}/json")
async def download_json_report(build_id: str, session=Depends(get_current_session)):
    path = os.path.join(REPORTS_DIR, f"{build_id}.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Report not yet generated.")
    return FileResponse(path, filename=f"fix_report_{build_id[:8]}.json", media_type="application/json")
