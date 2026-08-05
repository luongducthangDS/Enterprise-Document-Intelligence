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

        monkeypatch.setattr(fpt_client.requests, "post", fake_post)
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

        monkeypatch.setattr(fpt_client.requests, "post", fake_post)
        result = fpt_client.embed_batch(["a"], model="m", base_url="https://fake.example", api_key="k", retries=2)
        assert result == [[9.0]]
        assert calls["n"] == 2

    def test_raises_after_exhausting_retries(self, monkeypatch):
        _no_sleep(monkeypatch)

        def fake_post(url, headers, json, timeout):
            raise requests.exceptions.ConnectionError("always fails")

        monkeypatch.setattr(fpt_client.requests, "post", fake_post)
        try:
            fpt_client.embed_batch(["a"], model="m", base_url="https://fake.example", api_key="k", retries=1)
            assert False, "phải raise sau khi hết retries"
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

        monkeypatch.setattr(fpt_client.requests, "post", fake_post)
        out = fpt_client.chat_completion("sys", "usr", model="GLM-5.2", base_url="https://fake.example", api_key="k")
        assert out == "câu trả lời"

    def test_falls_back_to_reasoning_content(self, monkeypatch):
        _no_sleep(monkeypatch)

        def fake_post(url, headers, json, timeout):
            return FakeResponse({"choices": [{"message": {"reasoning_content": "suy luận"}}]})

        monkeypatch.setattr(fpt_client.requests, "post", fake_post)
        out = fpt_client.chat_completion("sys", "usr", model="GLM-5.2", base_url="https://fake.example", api_key="k")
        assert out == "suy luận"


class TestExtractPageMarkdown:
    def test_builds_image_and_prompt_payload(self, monkeypatch):
        _no_sleep(monkeypatch)
        captured = {}

        def fake_post(url, headers, json, timeout):
            captured["json"] = json
            return FakeResponse({"choices": [{"message": {"content": "# Trang 1"}}]})

        monkeypatch.setattr(fpt_client.requests, "post", fake_post)
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
