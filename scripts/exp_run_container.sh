#!/usr/bin/env bash
# 설정 하나를 CPU·메모리를 제한한 컨테이너에서 돌린다(모든 설정이 같은 이미지·같은 한도).
#   scripts/exp_run_container.sh <label> <env-file> <variable> <value>
#   variable: baseline | chunk_size | overlap | topk | context_size | rerank_candidates   (baseline은 value 생략 가능)
set -euo pipefail

usage() { echo "사용: $0 <label> <env-file> <baseline|chunk_size|overlap|topk|context_size|rerank_candidates> [value]" >&2; exit 2; }
[[ $# -ge 3 ]] || usage
label=$1; env_file=$2; variable=$3; value=${4:-}
[[ "$label" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || { echo "라벨이 올바르지 않다: $label" >&2; exit 2; }
[[ -f "$env_file" ]] || { echo "env 파일이 없다: $env_file" >&2; exit 2; }

modes=naive,hybrid,hybrid_rerank
case "$variable" in
  baseline) [[ -z "$value" ]] || usage; extra=() ;;
  chunk_size)         extra=(-e "EXP_CHUNK_SIZE=$value") ;;
  overlap)            extra=(-e "EXP_CHUNK_OVERLAP=$value") ;;
  topk)               extra=(-e "EXP_TOPK=$value") ;;
  context_size)       extra=(-e "EXP_CONTEXT_TOKENS=$value") ;;
  rerank_candidates)  extra=(-e "EXP_RERANK_CANDIDATES=$value"); modes=hybrid_rerank ;;  # 이 방식에만 영향이 있다
  *) usage ;;
esac
[[ "$variable" == baseline ]] || [[ "$value" =~ ^[0-9]+$ ]] || { echo "value는 정수여야 한다: $value" >&2; exit 2; }

repo_root=$(cd "$(dirname "$0")/.." && pwd)
env_file=$(cd "$(dirname "$env_file")" && pwd)/$(basename "$env_file")
name="exp2-$label"
hf_cache="$HOME/.cache/huggingface"
[[ -d "$hf_cache/hub" ]] || { echo "HF 캐시($hf_cache/hub)가 없다. 모델 가중치를 호스트에서 먼저 받아 둬야 한다" >&2; exit 1; }
if docker container inspect "$name" >/dev/null 2>&1; then echo "컨테이너가 이미 있다: $name" >&2; exit 1; fi

# 색인 폴더는 컨테이너 안에서 새로 만들어야 하므로 상위 폴더만 마운트한다
mkdir -p "$repo_root/.scratch/idx" "$repo_root/results/exp2"
image_id=$(docker image inspect --format '{{.Id}}' exp2:local)
echo "image=$image_id label=$label variable=$variable value=${value:--}"

exec docker run --rm --name "$name" --cpus=3 --memory=4g --memory-swap=4g \
  -e OMP_NUM_THREADS=3 -e MKL_NUM_THREADS=3 \
  -e "EXP_INDEX_DIR=/app/.scratch/idx/$label" -e "EXP_LABEL=$label" \
  -e "EXP_VARIABLE=$variable" -e "EXP_VALUE=${value:--}" -e "EXP_MODES=$modes" -e "EXP_IMAGE_ID=$image_id" \
  ${extra[@]+"${extra[@]}"} \
  --env-file "$env_file" \
  --mount "type=bind,src=$repo_root/data,dst=/app/data,readonly" \
  --mount "type=bind,src=$repo_root/.scratch/idx,dst=/app/.scratch/idx" \
  --mount "type=bind,src=$repo_root/results/exp2,dst=/app/results/exp2" \
  --mount "type=bind,src=$hf_cache,dst=/root/.cache/huggingface,readonly" \
  exp2:local bash scripts/exp_pipeline.sh
