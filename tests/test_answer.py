from src.answer.chain import _messages, system_prompt
from src.contracts import ChunkMeta, ContextChunk


def test_서비스_지시와_질문과_검색_자료를_구분한다():
    meta = ChunkMeta(book_id="SB01", file_name="SB01.pdf", page=2, chunk_id="SB01-p2-c1")
    system, user = _messages("질문", [ContextChunk(source_id="S1", text="본문", metadata=meta)])
    assert system["role"] == "system" and "본문" not in system["content"]
    assert user["role"] == "user"
    assert user["content"].startswith("[질문]\n질문\n\n[검색 자료]\n[S1]\n본문")


def test_모델에는_문서명과_페이지를_보여_주지_않는다():
    meta = ChunkMeta(book_id="SB01", file_name="SB01.pdf", page=2, chunk_id="SB01-p2-c1")
    _, user = _messages("질문", [ContextChunk(source_id="S1", text="본문", metadata=meta)])
    assert "SB01" not in user["content"] and "SB01.pdf" not in user["content"]


def test_프롬프트에는_날짜만으로_고르지_않는_지시가_있다():
    assert "날짜가 늦거나 앞에 놓였다는 이유만으로 고르지 않습니다" in system_prompt()


def test_프롬프트가_상태별_출처_규칙을_밝힌다():
    prompt = system_prompt()
    assert "answered이면 source_ids가 비어 있으면 안 됩니다" in prompt
    assert "문서 ID, 파일명, 페이지는 answer와 reason 어디에도 쓰지 않습니다" in prompt
