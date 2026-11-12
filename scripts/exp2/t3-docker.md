<task>
[T3 설정별 Docker 실행 환경] 브랜치 exp/exp2-docker.
설정 하나를 CPU·메모리를 제한한 컨테이너에서 돌리는 환경을 만든다.
1. `docker/exp2/Dockerfile`: python:3.12-slim 기반, uv로 `uv sync --frozen`(pyproject.toml·uv.lock 그대로, 의존성 추가 금지), 소스는 `COPY src scripts pyproject.toml uv.lock`. 비밀값(.env)을 이미지에 넣지 않는다. 플랫폼은 호스트(Apple Silicon, linux/arm64)를 쓴다. torch 등이 linux aarch64 CPU 휠로 설치되는지 uv.lock의 wheel 목록으로 확인하고, 안 되면 이유를 보고한다(우회 의존성 추가는 하지 않는다).
2. `scripts/exp_run_container.sh <label> <command...>`: 위 이미지를 `docker run --rm`으로 실행한다. 고정 옵션: `--cpus=3 --memory=6g -e OMP_NUM_THREADS=3 -e MKL_NUM_THREADS=3`, `--env-file`로 비밀값은 실행 시에만 주입(호스트 .env 경로는 인자로 받고 스크립트에 값을 쓰지 않음), 마운트: `data`(읽기 전용), 설정별 색인 폴더 `<repo>/.scratch/idx/<label>`(읽기·쓰기), `results/exp2`(쓰기), Hugging Face 캐시(`~/.cache/huggingface`, 읽기 전용; 없으면 컨테이너 안 캐시 사용을 보고). 컨테이너 이름은 `exp2-<label>`로 고정해 같은 이름이 이미 돌고 있으면 시작하지 않는다.
3. `docker/exp2/README.md`(한 화면 분량): 이미지 빌드 명령, 한 컨테이너 실행 예, 5개 병렬 실행 예(변수당 1개), 이 호스트의 Docker Desktop VM 메모리가 현재 7.7GB라 5개×6GB를 못 올리므로 32GB 이상으로 올려야 한다는 안내, Linux VM은 MPS를 못 써서 리랭커가 CPU에서 느리다는 한계(로컬 측정: 20쌍 리랭크 MPS 0.33초, CPU 3스레드 2.65초).
Docker Desktop 설정과 다른 컨테이너·이미지는 건드리지 않는다.
</task>

<completeness_contract>
이미지를 실제로 빌드하고(`docker build`) `docker run --rm --cpus=3 --memory=6g <이미지> uv run python -c "import torch, sentence_transformers, qdrant_client; print(torch.__version__)"`로 import가 되는지 확인한다. VM 메모리가 부족해 빌드·실행이 실패하면 실패 원인과 필요한 메모리를 그대로 보고한다. LLM·Langfuse 호출과 색인 실행은 하지 않는다.
</completeness_contract>
