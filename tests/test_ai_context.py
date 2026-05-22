import unittest
from unittest.mock import patch

from services.ai_context import GIB, HardwareSnapshot, next_context_length, recommend_context_length


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
        self.assertIn("显存未知", recommendation.display_text)

    def test_display_text_only_shows_total_memory_and_vram(self):
        recommendation = recommend_context_length(
            hardware=hardware(15.6, available_gib=3.3, vram_gib=4),
            model_limit=131072,
            fetch_model_limit=False,
        )

        self.assertIn("15.6GB 内存", recommendation.display_text)
        self.assertIn("4GB 显存", recommendation.display_text)
        self.assertNotIn("自动", recommendation.display_text)
        self.assertNotIn("可用", recommendation.display_text)
        self.assertNotIn("模型上限", recommendation.display_text)
        self.assertEqual(2048, recommendation.n_ctx)
        self.assertEqual(8192, recommendation.max_n_ctx)

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

    def test_next_context_length_uses_next_step_within_maximum(self):
        self.assertEqual(4096, next_context_length(2048, 8192))
        self.assertEqual(8192, next_context_length(4096, 16384))
        self.assertEqual(16384, next_context_length(8192, 16384))
        self.assertEqual(32768, next_context_length(16384, 65536))
        self.assertEqual(6144, next_context_length(4096, 6144))
        self.assertIsNone(next_context_length(8192, 8192))


if __name__ == "__main__":
    unittest.main()
