#!/usr/bin/env python3
"""Run a private hidden-tests pipeline through GitLab trigger/read tokens."""

from __future__ import annotations

import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile


POLL_INTERVAL_SECONDS = 5.0
DEFAULT_TIMEOUT_SECONDS = 1800.0
FINISHED_STATUSES = {"success", "failed", "canceled", "skipped"}


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _json_request(url: str, *, read_token: str | None = None) -> dict | list:
    headers = {"PRIVATE-TOKEN": read_token} if read_token else {}
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitLab API returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitLab API is unavailable: {exc.reason}") from exc


def trigger_pipeline(
    api_url: str,
    project_id: str,
    trigger_token: str,
    upstream_project_id: str,
    upstream_pipeline_id: str,
    upstream_job_name: str,
) -> int:
    data = urllib.parse.urlencode(
        {
            "token": trigger_token,
            "ref": "main",
            "variables[UPSTREAM_PROJECT_ID]": upstream_project_id,
            "variables[UPSTREAM_PIPELINE_ID]": upstream_pipeline_id,
            "variables[UPSTREAM_JOB_NAME]": upstream_job_name,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{api_url.rstrip('/')}/projects/{urllib.parse.quote(project_id, safe='')}/trigger/pipeline",
        data=data,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Could not trigger hidden pipeline: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not trigger hidden pipeline: {exc.reason}") from exc
    try:
        pipeline_id = int(payload["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("GitLab returned an invalid hidden pipeline response") from exc
    print(f"Triggered hidden pipeline id={pipeline_id} (project={project_id})", flush=True)
    return pipeline_id


def _find_job_id_by_name(api_url: str, project_id: str, pipeline_id: int, read_token: str, job_name: str) -> int | None:
    url = (
        f"{api_url.rstrip('/')}/projects/{urllib.parse.quote(project_id, safe='')}"
        f"/pipelines/{pipeline_id}/jobs?per_page=100"
    )
    try:
        payload = _json_request(url, read_token=read_token)
    except RuntimeError:
        return None
    for job in payload if isinstance(payload, list) else []:
        if job.get("name") == job_name:
            return int(job["id"])
    return None


def _fetch_trace(api_url: str, project_id: str, job_id: int, read_token: str) -> str | None:
    url = f"{api_url.rstrip('/')}/projects/{urllib.parse.quote(project_id, safe='')}/jobs/{job_id}/trace"
    request = urllib.request.Request(url, headers={"PRIVATE-TOKEN": read_token})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise RuntimeError(f"Could not fetch job trace: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not fetch job trace: {exc.reason}") from exc


def wait_for_pipeline(
    api_url: str,
    project_id: str,
    pipeline_id: int,
    read_token: str,
    poll_interval: float = POLL_INTERVAL_SECONDS,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    job_name: str = "hidden_tests",
) -> str:
    url = f"{api_url.rstrip('/')}/projects/{urllib.parse.quote(project_id, safe='')}/pipelines/{pipeline_id}"
    deadline = time.monotonic() + timeout_seconds
    job_id: int | None = None
    trace_printed_len = 0
    while True:
        payload = _json_request(url, read_token=read_token)
        status = str(payload.get("status", "unknown"))
        elapsed = timeout_seconds - (deadline - time.monotonic())
        print(f"Polling hidden pipeline id={pipeline_id}: status={status} (elapsed={elapsed:.0f}s)", flush=True)

        if job_id is None:
            job_id = _find_job_id_by_name(api_url, project_id, pipeline_id, read_token, job_name)
            if job_id is not None:
                print(f"Found {job_name} job id={job_id}, streaming its trace", flush=True)

        if job_id is not None:
            trace = _fetch_trace(api_url, project_id, job_id, read_token)
            if trace and len(trace) > trace_printed_len:
                new_output = trace[trace_printed_len:]
                trace_printed_len = len(trace)
                for line in new_output.splitlines():
                    print(f"[{job_name}] {line}", flush=True)

        if status in FINISHED_STATUSES:
            return status
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Hidden pipeline timed out after {timeout_seconds:.0f}s (last status={status})")
        time.sleep(poll_interval)


def _find_hidden_job_id(api_url: str, project_id: str, pipeline_id: int, read_token: str) -> int:
    job_id = _find_job_id_by_name(api_url, project_id, pipeline_id, read_token, "hidden_tests")
    if job_id is None:
        raise RuntimeError("hidden_tests job was not found in the downstream pipeline")
    return job_id


def fetch_score(api_url: str, project_id: str, pipeline_id: int, read_token: str) -> str:
    job_id = _find_hidden_job_id(api_url, project_id, pipeline_id, read_token)
    url = f"{api_url.rstrip('/')}/projects/{urllib.parse.quote(project_id, safe='')}/jobs/{job_id}/artifacts"
    request = urllib.request.Request(url, headers={"PRIVATE-TOKEN": read_token})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            archive = io.BytesIO(response.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Could not download hidden score: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not download hidden score: {exc.reason}") from exc

    try:
        with zipfile.ZipFile(archive) as handle:
            score = json.loads(handle.read("score.json").decode("utf-8"))
        if "score" in score and "max_score" in score:
            return f"{score['score']} / {score['max_score']}"
        return f"{score['earned']} / {score['total']}"
    except (KeyError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        raise RuntimeError("Hidden pipeline artifact does not contain a valid score.json") from exc


def main() -> int:
    api_url = require_env("CI_API_V4_URL")
    pipeline_id = trigger_pipeline(
        api_url,
        require_env("HIDDEN_TESTS_PROJECT_ID"),
        require_env("HIDDEN_TESTS_TRIGGER_TOKEN"),
        require_env("CI_PROJECT_ID"),
        require_env("CI_PIPELINE_ID"),
        os.environ.get("UPSTREAM_JOB_NAME", "public_tests"),
    )
    status = wait_for_pipeline(
        api_url,
        require_env("HIDDEN_TESTS_PROJECT_ID"),
        pipeline_id,
        require_env("HIDDEN_TESTS_READ_TOKEN"),
        timeout_seconds=float(os.environ.get("HIDDEN_TESTS_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)),
    )
    score = fetch_score(api_url, require_env("HIDDEN_TESTS_PROJECT_ID"), pipeline_id, require_env("HIDDEN_TESTS_READ_TOKEN"))
    print(f"Hidden tests: {status}, score {score}")
    return 0 if status == "success" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"Hidden tests failed: {exc}", file=__import__("sys").stderr)
        raise SystemExit(1)
