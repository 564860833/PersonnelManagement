import unittest
from unittest.mock import patch

from services.ai_context import (
    GIB,
    HardwareSnapshot,
    clear_context_recommendation_cache,
    recommend_context_length,
)


class FakeShowResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def hardware(total_gib, available_gib=None, vram_gib=None):
    return HardwareSnapshot(
        total_memory_bytes=int(total_gib * GIB) if total_gib is not None else None,
        available_memory_bytes=int((available_gib if available_gib is not None else total_gib) * GIB)
        if total_gib is not None
        else None,
        gpu_vram_bytes=int(vram_gib * GIB) if vram_gib is not None else None,
    )


class AIContextRecommendationTests(unittest.TestCase):
    def setUp(self):
        clear_context_recommendation_cache()

    def test_recommends_low_context_for_low_memory_device(self):
        recommendation = recommend_context_length(
            hardware=hardware(6, available_gib=6),
            fetch_model_limit=False,
        )

        self.assertEqual(2048, recommendation.n_ctx)

    def test_recommends_default_context_for_standard_memory_device(self):
        recommendation = recommend_context_length(
            hardware=hardware(8, available_gib=8),
            fetch_model_limit=False,
        )

        self.assertEqual(4096, recommendation.n_ctx)

    def test_recommends_larger_context_for_mid_high_memory_or_vram(self):
        memory_recommendation = recommend_context_length(
            hardware=hardware(16, available_gib=16),
            fetch_model_limit=False,
        )
        vram_recommendation = recommend_context_length(
            hardware=hardware(12, available_gib=12, vram_gib=6),
            fetch_model_limit=False,
        )

        self.assertEqual(8192, memory_recommendation.n_ctx)
        self.assertEqual(8192, vram_recommendation.n_ctx)

    def test_recommends_max_context_for_high_memory_or_high_vram(self):
        memory_recommendation = recommend_context_length(
            hardware=hardware(32, available_gib=32),
            fetch_model_limit=False,
        )
        vram_recommendation = recommend_context_length(
            hardware=hardware(24, available_gib=24, vram_gib=8),
            fetch_model_limit=False,
        )

        self.assertEqual(16384, memory_recommendation.n_ctx)
        self.assertEqual(16384, vram_recommendation.n_ctx)

    def test_high_memory_device_can_exceed_old_fixed_maximum(self):
        recommendation = recommend_context_length(
            hardware=hardware(64, available_gib=64),
            fetch_model_limit=False,
        )

        self.assertEqual(32768, recommendation.n_ctx)
        self.assertEqual(32768, recommendation.max_n_ctx)

    def test_missing_vram_still_uses_system_memory(self):
        recommendation = recommend_context_length(
            hardware=hardware(16, available_gib=16, vram_gib=None),
            fetch_model_limit=False,
        )

        self.assertEqual(8192, recommendation.n_ctx)
        self.assertEqual("16GB 内存 / 显存未知", recommendation.reason)

    def test_available_memory_caps_recommendation(self):
        low_available = recommend_context_length(
            hardware=hardware(32, available_gib=3, vram_gib=8),
            fetch_model_limit=False,
        )
        moderate_available = recommend_context_length(
            hardware=hardware(32, available_gib=6, vram_gib=8),
            fetch_model_limit=False,
        )

        self.assertEqual(2048, low_available.n_ctx)
        self.assertEqual(4096, moderate_available.n_ctx)

    def test_detection_failure_uses_default_context(self):
        recommendation = recommend_context_length(
            hardware=HardwareSnapshot(),
            fetch_model_limit=False,
        )

        self.assertEqual(4096, recommendation.n_ctx)

    def test_show_api_model_limit_caps_recommendation(self):
        show_payload = {"model_info": {"qwen2.context_length": 8192}}

        with patch("services.ai_context.requests.post", return_value=FakeShowResponse(show_payload)) as post:
            recommendation = recommend_context_length(
                model_name="deepseek-r1:14b",
                hardware=hardware(32, available_gib=32, vram_gib=8),
                timeout=1,
            )

        self.assertEqual(8192, recommendation.n_ctx)
        self.assertEqual(8192, recommendation.model_limit)
        self.assertEqual({"model": "deepseek-r1:14b"}, post.call_args.kwargs["json"])

    def test_detect_hardware_is_cached_for_implicit_recommendations(self):
        snapshot = hardware(16, available_gib=16, vram_gib=4)

        with patch("services.ai_context.detect_hardware", return_value=snapshot) as detect:
            first = recommend_context_length(fetch_model_limit=False)
            second = recommend_context_length(fetch_model_limit=False)

        self.assertEqual(1, detect.call_count)
        self.assertEqual(first.n_ctx, second.n_ctx)
        self.assertEqual(snapshot, first.hardware)
        self.assertEqual(snapshot, second.hardware)

    def test_model_context_limit_is_cached_per_model_name(self):
        show_payload = {"model_info": {"qwen2.context_length": 8192}}
        snapshot = hardware(32, available_gib=32, vram_gib=8)

        with patch("services.ai_context.requests.post", return_value=FakeShowResponse(show_payload)) as post:
            first = recommend_context_length(
                model_name="deepseek-r1:14b",
                hardware=snapshot,
            )
            second = recommend_context_length(
                model_name="deepseek-r1:14b",
                hardware=snapshot,
            )

        self.assertEqual(1, post.call_count)
        self.assertEqual(8192, first.model_limit)
        self.assertEqual(8192, second.model_limit)

    def test_model_context_limit_cache_is_separate_per_model_name(self):
        first_payload = {"model_info": {"qwen2.context_length": 4096}}
        second_payload = {"model_info": {"qwen2.context_length": 8192}}
        snapshot = hardware(32, available_gib=32, vram_gib=8)

        with patch("services.ai_context.requests.post", side_effect=[
            FakeShowResponse(first_payload),
            FakeShowResponse(second_payload),
        ]) as post:
            first = recommend_context_length(model_name="model-a", hardware=snapshot)
            second = recommend_context_length(model_name="model-b", hardware=snapshot)

        self.assertEqual(2, post.call_count)
        self.assertEqual(4096, first.model_limit)
        self.assertEqual(8192, second.model_limit)

    def test_clear_context_recommendation_cache_resets_implicit_detection_and_model_cache(self):
        snapshot = hardware(16, available_gib=16, vram_gib=4)
        show_payload = {"model_info": {"qwen2.context_length": 8192}}

        with patch("services.ai_context.detect_hardware", return_value=snapshot) as detect, \
                patch("services.ai_context.requests.post", return_value=FakeShowResponse(show_payload)) as post:
            recommend_context_length(model_name="deepseek-r1:14b")
            clear_context_recommendation_cache()
            recommend_context_length(model_name="deepseek-r1:14b")

        self.assertEqual(2, detect.call_count)
        self.assertEqual(2, post.call_count)


if __name__ == "__main__":
    unittest.main()
