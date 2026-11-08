기준 문서: [docs/specs/platform.md](../../docs/specs/platform.md). 공용 타입은 `src/contracts.py`.

연결 점검: 레포 루트에서 `uv run python -m src.platform.check_connections`.
팀원 확인 절차와 미완료 항목은 루트 README의 "공용 서비스 연결 점검 (#40)"에 있다.

연결 점검 자가 확인 (외부 접속 없음): 미설정 시 클라이언트를 열지 않고, 실패 응답의 비밀값을 출력하지 않는지 확인한다.

```bash
uv run python - <<'PY'
from unittest.mock import patch
from src.platform import check_connections as check

with patch.object(check.config, 'QDRANT_URL', None), patch.object(check.config, 'env', return_value=None), patch.object(check.store, 'get_client') as store, patch.object(check.tracing, 'get_client') as trace:
    assert all(v.startswith('not_configured:') for v in check.check_connections().values())
    store.assert_not_called()
    trace.assert_not_called()

with patch.object(check.config, 'QDRANT_URL', 'https://example.invalid'), patch.object(check.config, 'env', return_value='test'), patch.object(check.store, 'get_client', side_effect=RuntimeError('secret-response')), patch.object(check.store, 'reset_client'), patch.object(check.tracing, 'get_client', side_effect=RuntimeError('secret-response')):
    assert check.check_connections() == {'qdrant': 'failed: RuntimeError', 'langfuse': 'failed: RuntimeError'}
print('connection check self-check: passed')
PY
```
