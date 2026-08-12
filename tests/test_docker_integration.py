import json
import subprocess
import time
import requests
import pytest


def docker_available():
    try:
        subprocess.run(["docker", "version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


@pytest.mark.skipif(not docker_available(), reason="Docker is not available")
def test_docker_image_exists():
    result = subprocess.run(
        ["docker", "image", "inspect", "secur-app"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    info = json.loads(result.stdout)
    assert any("secur-app:latest" in tag for tag in info[0].get("RepoTags", []))


@pytest.mark.skipif(not docker_available(), reason="Docker is not available")
def test_docker_container_health():
    container_name = "secur_test_integration"
    run_proc = subprocess.Popen(
        ["docker", "run", "--rm", "--name", container_name, "-p", "8003:8000", "secur-app"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        for _ in range(20):
            if run_proc.poll() is not None:
                stdout, stderr = run_proc.communicate(timeout=1)
                raise AssertionError(f"Container exited early: {stderr.decode('utf-8', errors='ignore')}" )
            try:
                response = requests.get("http://localhost:8003/health", timeout=2)
                if response.status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(1)
        else:
            raise AssertionError("Container did not become healthy in time")

        assert response.json()["status"] == "ok"
        docs_response = requests.get("http://localhost:8003/docs", timeout=2)
        assert docs_response.status_code == 200
    finally:
        subprocess.run(["docker", "stop", container_name], capture_output=True)
        if run_proc.poll() is None:
            run_proc.terminate()
            run_proc.wait(timeout=10)
