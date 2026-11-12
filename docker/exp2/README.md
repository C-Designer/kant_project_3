# EXP-0002 Docker 실행

모든 설정이 **같은 이미지(`exp2:local`)·같은 한도(CPU 3, 메모리 4GB)·같은 파이프라인**(`scripts/exp_pipeline.sh`: 컨테이너 안에서 새 색인 → LLM 없는 검색 지표 → Langfuse 실험)으로 돈다. 가중치는 호스트 HF 캐시를 읽기 전용으로 마운트하고 `HF_HUB_OFFLINE=1`이라 모든 컨테이너가 같은 가중치를 쓴다.

```bash
docker build -f docker/exp2/Dockerfile -t exp2:local .            # 저장소 루트에서. 의존성 층은 캐시된다
scripts/exp_run_container.sh baseline  .env baseline              # 기준 설정
scripts/exp_run_container.sh chunk-600 .env chunk_size 600        # 변수 하나만 바꾼 설정
scripts/exp_run_container.sh overlap-100 .env overlap 100
scripts/exp_run_container.sh topk-3 .env topk 3
scripts/exp_run_container.sh ctx-1000 .env context_size 1000
scripts/exp_run_container.sh rerank-10 .env rerank_candidates 10  # hybrid_rerank 하나만 돈다
```

`<env-file>`은 호스트의 파일 경로이며 이미지에 복사되지 않는다. 결과는 `results/exp2/<label>-retrieval.csv`와 Langfuse(run 이름에 설정 라벨).

## 동시에 몇 개까지 띄울 수 있나 (실측, 2026-11-12)

- 컨테이너 하나의 최대 메모리 2.8GB(임베딩+리랭커). 한도는 4GB.
- 이 호스트의 Docker VM은 7.7GB이고 **팀 공용 Langfuse·ClickHouse·Qdrant 컨테이너가 같은 VM에서 약 2.5GB를 쓴다.** 그래서 VM 설정을 올리기 전에는 **한 번에 컨테이너 1개만** 띄운다(2개면 VM 메모리를 넘겨 공용 서비스가 OOM으로 죽을 수 있다).
- Linux VM은 호스트 GPU(MPS)를 못 써서 리랭커가 CPU에서 느리다. 20쌍 리랭크: MPS 0.33초, 호스트 CPU 3스레드 2.65초, **컨테이너 12.1초**. 컨테이너에서 잰 응답 시간은 호스트 실행과 절대값으로 비교하지 않고, 같은 컨테이너 환경의 기준 설정과만 비교한다.
