import pytest
import requests

from src.services import fpt_client


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._json


def _no_sleep(monkeypatch):
    monkeypatch.setattr(fpt_client.time, "sleep", lambda _seconds: None)


def _patch_post(monkeypatch, fake_post):
    # Mọi call đi qua Session dùng chung của module (connection pooling) —
    # patch trên đó chứ không phải requests.post.
    monkeypatch.setattr(fpt_client._session, "post", fake_post)


class TestRetryWithBackoff:
    def test_no_sleep_on_immediate_success(self, monkeypatch):
        sleeps: list[float] = []
        monkeypatch.setattr(fpt_client.time, "sleep", sleeps.append)

        assert fpt_client._retry_with_backoff(lambda: "ok", retries=2) == "ok"
        assert sleeps == []

    def test_backoff_delays_grow_exponentially(self, monkeypatch):
        """Regression: sleep 2s cố định từng làm mất 9-12 câu/lần chạy eval khi
        gateway lỗi thoáng qua — delay phải tăng dần để chờ gateway hồi."""
        sleeps: list[float] = []
        monkeypatch.setattr(fpt_client.time, "sleep", sleeps.append)
        # Jitter cố định 0 để delay xác định được trong test.
        monkeypatch.setattr(fpt_client.random, "uniform", lambda _a, _b: 0.0)

        def always_fail():
            raise requests.exceptions.ConnectionError("boom")

        try:
            fpt_client._retry_with_backoff(always_fail, retries=3)
            raise AssertionError("phải raise sau khi hết retries")
        except requests.exceptions.ConnectionError:
            pass

        # 3 retries -> 3 lần sleep giữa 4 lần thử: 1s, 2s, 4s
        assert sleeps == [1.0, 2.0, 4.0]

    def test_delay_is_capped(self, monkeypatch):
        sleeps: list[float] = []
        monkeypatch.setattr(fpt_client.time, "sleep", sleeps.append)
        monkeypatch.setattr(fpt_client.random, "uniform", lambda _a, _b: 0.0)

        def always_fail():
            raise requests.exceptions.ConnectionError("boom")

        try:
            fpt_client._retry_with_backoff(always_fail, retries=5)
            raise AssertionError("phải raise sau khi hết retries")
        except requests.exceptions.ConnectionError:
            pass

        # 1, 2, 4, rồi chạm trần 8 — không phình lên 16/32.
        assert sleeps == [1.0, 2.0, 4.0, 8.0, 8.0]

    def test_does_not_retry_non_network_errors(self, monkeypatch):
        """Lỗi lập trình (KeyError khi parse response...) phải nổ ngay, không bị
        nuốt vào vòng retry như thể là lỗi mạng."""
        sleeps: list[float] = []
        monkeypatch.setattr(fpt_client.time, "sleep", sleeps.append)
        calls = {"n": 0}

        def bad_parse():
            calls["n"] += 1
            raise KeyError("choices")

        try:
            fpt_client._retry_with_backoff(bad_parse, retries=3)
            raise AssertionError("phải raise KeyError")
        except KeyError:
            pass
        assert calls["n"] == 1
        assert sleeps == []


class TestEmbedBatch:
    def test_reorders_by_index(self, monkeypatch):
        _no_sleep(monkeypatch)

        def fake_post(url, headers, json, timeout):
            assert url == "https://fake.example/embeddings"
            # API trả về không đúng thứ tự input
            return FakeResponse({"data": [
                {"index": 1, "embedding": [2.0]},
                {"index": 0, "embedding": [1.0]},
            ]})

        _patch_post(monkeypatch, fake_post)
        result = fpt_client.embed_batch(["a", "b"], model="m", base_url="https://fake.example", api_key="k")
        assert result == [[1.0], [2.0]]

    def test_retries_then_succeeds(self, monkeypatch):
        _no_sleep(monkeypatch)
        calls = {"n": 0}

        def fake_post(url, headers, json, timeout):
            calls["n"] += 1
            if calls["n"] < 2:
                raise requests.exceptions.ConnectionError("boom")
            return FakeResponse({"data": [{"index": 0, "embedding": [9.0]}]})

        _patch_post(monkeypatch, fake_post)
        result = fpt_client.embed_batch(["a"], model="m", base_url="https://fake.example", api_key="k", retries=2)
        assert result == [[9.0]]
        assert calls["n"] == 2

    def test_raises_after_exhausting_retries(self, monkeypatch):
        _no_sleep(monkeypatch)

        def fake_post(url, headers, json, timeout):
            raise requests.exceptions.ConnectionError("always fails")

        _patch_post(monkeypatch, fake_post)
        try:
            fpt_client.embed_batch(["a"], model="m", base_url="https://fake.example", api_key="k", retries=1)
            raise AssertionError("phải raise sau khi hết retries")
        except requests.exceptions.ConnectionError:
            pass


class TestChatCompletion:
    def test_returns_content(self, monkeypatch):
        _no_sleep(monkeypatch)

        def fake_post(url, headers, json, timeout):
            assert url == "https://fake.example/chat/completions"
            assert json["messages"][0] == {"role": "system", "content": "sys"}
            assert json["messages"][1] == {"role": "user", "content": "usr"}
            assert json["temperature"] == 0.5
            return FakeResponse({"choices": [{"message": {"content": "câu trả lời"}}]})

        _patch_post(monkeypatch, fake_post)
        out = fpt_client.chat_completion("sys", "usr", model="GLM-5.2", base_url="https://fake.example", api_key="k")
        assert out == "câu trả lời"

    def test_falls_back_to_reasoning_content(self, monkeypatch):
        _no_sleep(monkeypatch)

        def fake_post(url, headers, json, timeout):
            return FakeResponse({"choices": [{"message": {"reasoning_content": "suy luận"}}]})

        _patch_post(monkeypatch, fake_post)
        out = fpt_client.chat_completion("sys", "usr", model="GLM-5.2", base_url="https://fake.example", api_key="k")
        assert out == "suy luận"

    def test_omits_thinking_field_by_default(self, monkeypatch):
        """Không truyền enable_thinking -> payload không có chat_template_kwargs,
        tức mọi caller cũ (script ingest, eval judge) giữ nguyên hành vi model."""
        _no_sleep(monkeypatch)
        captured = {}

        def fake_post(url, headers, json, timeout):
            captured["json"] = json
            return FakeResponse({"choices": [{"message": {"content": "ok"}}]})

        _patch_post(monkeypatch, fake_post)
        fpt_client.chat_completion("sys", "usr", model="GLM-5.2", base_url="https://fake.example", api_key="k")
        assert "chat_template_kwargs" not in captured["json"]

    def test_sends_disable_thinking_flag(self, monkeypatch):
        """enable_thinking=False phải xuống gateway đúng dạng
        chat_template_kwargs — đây là dạng duy nhất gateway FPT chấp nhận
        (reasoning_effort trả 200 nhưng vẫn sinh đủ reasoning token)."""
        _no_sleep(monkeypatch)
        captured = {}

        def fake_post(url, headers, json, timeout):
            captured["json"] = json
            return FakeResponse({"choices": [{"message": {"content": "hr_question"}}]})

        _patch_post(monkeypatch, fake_post)
        fpt_client.chat_completion(
            "sys",
            "usr",
            model="DeepSeek-V4-Flash",
            base_url="https://fake.example",
            api_key="k",
            enable_thinking=False,
        )
        assert captured["json"]["chat_template_kwargs"] == {"enable_thinking": False}

    def test_524_fails_fast_without_retry(self, monkeypatch):
        _no_sleep(monkeypatch)
        calls = 0

        def fake_post(url, headers, json, timeout):
            nonlocal calls
            calls += 1
            response = requests.Response()
            response.status_code = 524
            response.url = url
            raise requests.exceptions.HTTPError("524 upstream timeout", response=response)

        _patch_post(monkeypatch, fake_post)
        with pytest.raises(requests.exceptions.HTTPError):
            fpt_client.chat_completion(
                "sys",
                "usr",
                model="GLM-5.2",
                base_url="https://fake.example",
                api_key="k",
                retries=2,
            )

        assert calls == 1


class TestExtractPageMarkdown:
    def test_builds_image_and_prompt_payload(self, monkeypatch):
        _no_sleep(monkeypatch)
        captured = {}

        def fake_post(url, headers, json, timeout):
            captured["json"] = json
            return FakeResponse({"choices": [{"message": {"content": "# Trang 1"}}]})

        _patch_post(monkeypatch, fake_post)
        out = fpt_client.extract_page_markdown(
            b"\x89PNG-fake-bytes",
            prompt="Trích xuất trang này",
            model="Qwen2.5-VL-7B-Instruct",
            base_url="https://fake.example",
            api_key="k",
        )
        assert out == "# Trang 1"
        content = captured["json"]["messages"][0]["content"]
        assert content[0]["type"] == "image_url"
        assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")
        assert content[1] == {"type": "text", "text": "Trích xuất trang này"}
