#!/usr/bin/env bash
# 컨테이너 안에서 설정 하나를 처음부터 끝까지 돌린다. 기준·변수 설정이 같은 단계를 거치도록 이것만 쓴다.
#   1) 이 컨테이너 안에서 새 색인(EXP_INDEX_DIR)  2) LLM 없는 검색 지표  3) Langfuse 실험(Faithfulness, 운영 지표)
# 환경 변수: EXP_LABEL(필수), EXP_VARIABLE(기본 baseline), EXP_VALUE(기본 -), EXP_MODES, EXP_STAGES(기본 index,bench,llm)
set -euo pipefail

: "${EXP_LABEL:?EXP_LABEL이 필요하다}"
variable=${EXP_VARIABLE:-baseline}
value=${EXP_VALUE:--}
modes=${EXP_MODES:-naive,hybrid,hybrid_rerank}
stages=${EXP_STAGES:-index,bench,llm}
mkdir -p results/exp2

case ",$stages," in *,index,*) python -m scripts.exp_index ;; esac
case ",$stages," in *,bench,*) python scripts/exp_retrieval_bench.py --modes "$modes" --variable "$variable" --value "$value" --repeats "${EXP_REPEATS:-3}" \
  --out "results/exp2/$EXP_LABEL-retrieval.csv" ;; esac
case ",$stages," in *,llm,*) python scripts/lf_experiment.py --modes "$modes" --no-judge ;; esac
echo "pipeline 완료: $EXP_LABEL"
