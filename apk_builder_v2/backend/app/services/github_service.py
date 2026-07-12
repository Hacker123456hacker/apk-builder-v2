import asyncio
import base64
import httpx
from typing import Optional


class GitHubAPIError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class GitHubService:
    BASE_URL = "https://api.github.com"

    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _client(self):
        return httpx.AsyncClient(base_url=self.BASE_URL, headers=self.headers, timeout=30.0)

    async def validate_token(self) -> dict:
        async with await self._client() as client:
            res = await client.get("/user")
            if res.status_code != 200:
                return {"valid": False, "error": f"Invalid token (HTTP {res.status_code})", "user": None}
            scopes = {s.strip() for s in res.headers.get("x-oauth-scopes", "").split(",") if s.strip()}
            missing = [s for s in ("repo", "workflow") if s not in scopes]
            if missing:
                return {"valid": False, "error": f"Token missing scope(s): {', '.join(missing)}", "user": None}
            return {"valid": True, "error": None, "user": res.json()}

    async def get_authenticated_user(self) -> Optional[dict]:
        async with await self._client() as client:
            res = await client.get("/user")
            return res.json() if res.status_code == 200 else None

    async def get_repo(self, owner: str, repo: str) -> Optional[dict]:
        async with await self._client() as client:
            res = await client.get(f"/repos/{owner}/{repo}")
            return res.json() if res.status_code == 200 else None

    async def create_repo(self, name: str, private: bool = False) -> dict:
        async with await self._client() as client:
            res = await client.post("/user/repos", json={
                "name": name, "private": private,
                "auto_init": True, "description": "Created by AI APK Builder",
            })
            if res.status_code == 201:
                return res.json()
            raise GitHubAPIError(f"Failed to create repo: {self._err(res)}", res.status_code)

    async def get_or_create_repo(self, owner: str, name: str) -> dict:
        existing = await self.get_repo(owner, name)
        return existing or await self.create_repo(name)

    # ------------------------------------------------------------------
    # Legacy single-file Contents API — kept for callers that still need
    # to write/update one file at a time (e.g. small patches). Bulk
    # project uploads should use push_files() below instead, since that
    # uses the Git Data (Tree) API and creates ONE commit for the whole
    # project instead of one commit per file.
    # ------------------------------------------------------------------
    async def put_file(self, owner: str, repo: str, path: str, content: bytes, branch: str, message: str = None):
        async with await self._client() as client:
            sha = None
            ex = await client.get(f"/repos/{owner}/{repo}/contents/{path}", params={"ref": branch})
            if ex.status_code == 200 and isinstance(ex.json(), dict):
                sha = ex.json().get("sha")
            payload = {
                "message": message or f"Add {path}",
                "content": base64.b64encode(content).decode(),
                "branch": branch,
            }
            if sha:
                payload["sha"] = sha
            res = await client.put(f"/repos/{owner}/{repo}/contents/{path}", json=payload)
            if res.status_code not in (200, 201):
                raise GitHubAPIError(f"Failed to upload {path}: {self._err(res)}", res.status_code)

    # ------------------------------------------------------------------
    # Git Data (Tree) API — bulk upload in a single commit.
    # ------------------------------------------------------------------
    async def get_branch_sha(self, owner: str, repo: str, branch: str) -> Optional[str]:
        async with await self._client() as client:
            res = await client.get(f"/repos/{owner}/{repo}/git/ref/heads/{branch}")
            if res.status_code != 200:
                return None
            return res.json()["object"]["sha"]

    async def create_blob(self, client: httpx.AsyncClient, owner: str, repo: str, content: bytes) -> str:
        res = await client.post(f"/repos/{owner}/{repo}/git/blobs", json={
            "content": base64.b64encode(content).decode(),
            "encoding": "base64",
        })
        if res.status_code != 201:
            raise GitHubAPIError(f"Failed to create blob: {self._err(res)}", res.status_code)
        return res.json()["sha"]

    async def create_tree(self, owner: str, repo: str, base_tree_sha: str, tree_items: list) -> str:
        async with await self._client() as client:
            res = await client.post(f"/repos/{owner}/{repo}/git/trees", json={
                "base_tree": base_tree_sha,
                "tree": tree_items,
            })
            if res.status_code != 201:
                raise GitHubAPIError(f"Failed to create tree: {self._err(res)}", res.status_code)
            return res.json()["sha"]

    async def create_commit(self, owner: str, repo: str, message: str, tree_sha: str, parent_sha: str) -> str:
        async with await self._client() as client:
            res = await client.post(f"/repos/{owner}/{repo}/git/commits", json={
                "message": message,
                "tree": tree_sha,
                "parents": [parent_sha],
            })
            if res.status_code != 201:
                raise GitHubAPIError(f"Failed to create commit: {self._err(res)}", res.status_code)
            return res.json()["sha"]

    async def update_ref(self, owner: str, repo: str, branch: str, commit_sha: str, force: bool = False):
        async with await self._client() as client:
            res = await client.patch(f"/repos/{owner}/{repo}/git/refs/heads/{branch}", json={
                "sha": commit_sha,
                "force": force,
            })
            if res.status_code != 200:
                raise GitHubAPIError(f"Failed to update ref: {self._err(res)}", res.status_code)

    async def push_files(
        self,
        owner: str,
        repo: str,
        branch: str,
        files: dict,
        message: str = "Update via AI APK Builder",
        progress_cb=None,
        concurrency: int = 8,
    ) -> str:
        """
        Push an entire project as ONE commit using the Git Tree API.

        files: dict of {path_in_repo: bytes_content}
        progress_cb: optional callable(done, total, path) for progress updates.
        Returns the new commit sha.
        """
        base_sha = await self.get_branch_sha(owner, repo, branch)
        if base_sha is None:
            raise GitHubAPIError(f"Could not resolve branch ref for '{branch}'. Does the repo/branch exist?")

        total = len(files)
        done_counter = {"n": 0}
        sem = asyncio.Semaphore(concurrency)

        async def _one(client: httpx.AsyncClient, path: str, content: bytes):
            async with sem:
                sha = await self.create_blob(client, owner, repo, content)
            done_counter["n"] += 1
            if progress_cb:
                progress_cb(done_counter["n"], total, path)
            return path, sha

        async with await self._client() as client:
            results = await asyncio.gather(*[_one(client, p, c) for p, c in files.items()])

        tree_items = [
            {"path": path, "mode": "100644", "type": "blob", "sha": sha}
            for path, sha in results
        ]

        tree_sha = await self.create_tree(owner, repo, base_sha, tree_items)
        commit_sha = await self.create_commit(owner, repo, message, tree_sha, base_sha)
        await self.update_ref(owner, repo, branch, commit_sha)
        return commit_sha

    async def trigger_workflow(self, owner: str, repo: str, workflow_file: str, ref: str):
        async with await self._client() as client:
            res = await client.post(
                f"/repos/{owner}/{repo}/actions/workflows/{workflow_file}/dispatches",
                json={"ref": ref},
            )
            if res.status_code != 204:
                raise GitHubAPIError(f"Trigger failed: {self._err(res)}", res.status_code)

    async def find_latest_run(self, owner: str, repo: str, workflow_file: str) -> Optional[dict]:
        async with await self._client() as client:
            res = await client.get(f"/repos/{owner}/{repo}/actions/workflows/{workflow_file}/runs", params={"per_page": 5})
            if res.status_code != 200:
                return None
            runs = res.json().get("workflow_runs", [])
            return runs[0] if runs else None

    async def get_run(self, owner: str, repo: str, run_id: int) -> Optional[dict]:
        async with await self._client() as client:
            res = await client.get(f"/repos/{owner}/{repo}/actions/runs/{run_id}")
            return res.json() if res.status_code == 200 else None

    async def get_run_jobs(self, owner: str, repo: str, run_id: int) -> list:
        async with await self._client() as client:
            res = await client.get(f"/repos/{owner}/{repo}/actions/runs/{run_id}/jobs")
            return res.json().get("jobs", []) if res.status_code == 200 else []

    async def get_job_logs(self, owner: str, repo: str, job_id: int) -> Optional[str]:
        async with await self._client() as client:
            res = await client.get(f"/repos/{owner}/{repo}/actions/jobs/{job_id}/logs", follow_redirects=True)
            return res.text if res.status_code == 200 else None

    async def get_artifacts(self, owner: str, repo: str, run_id: int) -> list:
        async with await self._client() as client:
            res = await client.get(f"/repos/{owner}/{repo}/actions/runs/{run_id}/artifacts")
            return res.json().get("artifacts", []) if res.status_code == 200 else []

    async def download_artifact(self, url: str) -> Optional[bytes]:
        async with await self._client() as client:
            res = await client.get(url, follow_redirects=True)
            return res.content if res.status_code == 200 else None

    @staticmethod
    def _err(res) -> str:
        try:
            d = res.json()
            if isinstance(d, dict) and "message" in d:
                return d["message"]
        except Exception:
            pass
        return f"HTTP {res.status_code}"
