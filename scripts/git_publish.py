#!/usr/bin/env python3
"""
git_publish.py - Robust commit + push for the blog repo.

Usage: python3 git_publish.py "commit message"

Solves the problem of git commit/push hanging when run from osascript,
which leaves inherited pipe FDs open that git waits on indefinitely.

Strategy:
  1. Kill any stale git processes, clean ALL .lock files in .git/
  2. Stage content/posts/ static/images/ scripts/
  3. Create commit object directly (write-tree + commit-tree + write ref)
     - bypasses git commit's locking on refs/heads/main.lock
  4. Push via subprocess with start_new_session=True (clean FD set)
  5. Write output to /tmp/git_publish_output.txt for inspection
"""

import subprocess, os, sys, glob, signal

REPO = os.path.expanduser("~/Desktop/joaobonin.com")
OUT  = "/tmp/git_publish_output.txt"

def log(msg):
    print(msg)
    with open(OUT, "a") as f:
        f.write(msg + "\n")

def run(cmd, **kwargs):
    return subprocess.run(cmd, cwd=REPO, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=30, **kwargs)

def clean_locks():
    for lock in glob.glob(os.path.join(REPO, ".git/**/*.lock"), recursive=True):
        try:
            os.unlink(lock)
            log(f"  removed lock: {lock}")
        except Exception as e:
            log(f"  could not remove {lock}: {e}")
    # Also top-level
    for lock in glob.glob(os.path.join(REPO, ".git/*.lock")):
        try:
            os.unlink(lock)
            log(f"  removed lock: {lock}")
        except Exception as e:
            log(f"  could not remove {lock}: {e}")

def kill_stale_git():
    r = subprocess.run(["pgrep", "-f", "CommandLineTools/usr/bin/git"],
                       capture_output=True, text=True)
    pids = [p.strip() for p in r.stdout.splitlines() if p.strip()]
    for pid in pids:
        try:
            os.kill(int(pid), signal.SIGKILL)
            log(f"  killed stale git PID {pid}")
        except:
            pass

def git_stage():
    for path in ["content/posts/", "static/images/", "scripts/"]:
        r = run(["/usr/bin/git", "add", path])
        if r.returncode != 0:
            log(f"  git add {path} warning: {r.stderr.strip()}")

def git_commit(msg):
    # write-tree
    r = run(["/usr/bin/git", "write-tree"])
    if r.returncode != 0:
        raise RuntimeError(f"write-tree failed: {r.stderr.strip()}")
    tree = r.stdout.strip()
    log(f"  tree: {tree}")

    # commit-tree
    r2 = run(["/usr/bin/git", "commit-tree", tree, "-p", "HEAD", "-m", msg])
    if r2.returncode != 0:
        raise RuntimeError(f"commit-tree failed: {r2.stderr.strip()}")
    commit = r2.stdout.strip()
    log(f"  commit: {commit}")

    # write ref directly (bypasses refs/heads/main.lock hang)
    ref_path = os.path.join(REPO, ".git/refs/heads/main")
    with open(ref_path, "w") as f:
        f.write(commit + "\n")
    log(f"  ref updated -> {commit[:7]}")
    return commit

def git_push():
    r = subprocess.run(
        ["/usr/bin/git", "-C", REPO, "push", "origin", "main"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=90,
        start_new_session=True,
    )
    log(f"  push stdout: {r.stdout.strip()}")
    log(f"  push stderr: {r.stderr.strip()}")
    log(f"  push rc: {r.returncode}")
    return r.returncode

if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 else "auto-commit"

    # Reset output file
    with open(OUT, "w") as f:
        f.write(f"git_publish.py starting: {msg}\n")

    log("--- killing stale git processes ---")
    kill_stale_git()

    log("--- cleaning lock files ---")
    clean_locks()

    log("--- staging files ---")
    git_stage()

    log("--- committing ---")
    commit = git_commit(msg)

    log("--- pushing ---")
    rc = git_push()

    if rc == 0:
        log("DONE")
    else:
        log(f"PUSH FAILED (rc={rc})")
        sys.exit(1)
