import logging
import os
import time
from typing import TYPE_CHECKING, Any, Optional

import numpy as np

from light_map.core.analytics import LatencyInstrument, track_wait
from light_map.core.common_types import AppConfig, Layer


if TYPE_CHECKING:
    from light_map.rendering.projection import Projector3DModel


from light_map.rendering.composition_utils import composite_patch, covers_screen


class Renderer:
    """
    Coordinates the compositing of multiple visual layers into a final frame.
    Optimized with intermediate caching for static layers.
    """

    def __init__(
        self,
        config: "AppConfig",
        projector_3d_model: Optional["Projector3DModel"] = None,
    ):
        self.config = config
        self.projector_3d_model = projector_3d_model

        # Main output buffer (BGR)
        self.output_buffer = np.zeros((self.height, self.width, 3), dtype=np.uint8)

        # Version tracking: Dict[Layer, int]
        self.last_layer_versions = {}
        self._last_layer_stack: list[Layer] = []
        # LIGHT_MAP_LAYER_TIMING=1 logs, every 5 s, what each layer costs per composited frame
        self._timing_enabled = bool(os.environ.get("LIGHT_MAP_LAYER_TIMING"))
        self._timing: dict[str, list[float]] = {}
        self._timing_frames = 0
        self._timing_since = time.perf_counter()

    @property
    def width(self) -> int:
        return self.config.width

    @property
    def height(self) -> int:
        return self.config.height

    @property
    def screen_width(self) -> int:
        return self.width

    @property
    def screen_height(self) -> int:
        return self.height

    def render(
        self,
        state: Any,
        layers: list[Layer],
        current_time: float = 0.0,
        instrument: LatencyInstrument | None = None,
    ) -> np.ndarray | None:
        """
        Composites all provided layers into the final output buffer.
        Returns None if no layers requested a new render and compositing was skipped.

        Args:
            state: The current WorldState (optional, layers use their own injected state).
            layers: A list of Layer objects, from bottom to top.
            current_time: The current application time (monotonic).
            instrument: Optional LatencyInstrument to track per-layer timings.
        """
        # 1. Check if stack changed
        stack_changed = layers != self._last_layer_stack
        if stack_changed:
            self._last_layer_stack = list(layers)

        should_composite_frame = stack_changed

        # Check for any version changes
        for layer in layers:
            layer_version = layer.get_current_version()
            if layer_version != self.last_layer_versions.get(layer, -1):
                should_composite_frame = True

        if not should_composite_frame:
            return None

        # 2. Composite All Layers
        self.output_buffer.fill(0)
        rendered_layers = []
        for layer in layers:
            started = time.perf_counter()
            with track_wait(f"layer_render_{layer.__class__.__name__}", instrument):
                layer_patches, layer_version = layer.render(current_time)
                self.last_layer_versions[layer] = layer_version
            rendered_layers.append((layer, layer_patches, time.perf_counter() - started))

        # Layers under a patch that hides the whole screen cannot be seen: do not blend them.
        first_visible = 0
        for index, (layer, layer_patches, _spent) in enumerate(rendered_layers):
            if layer_patches and any(
                covers_screen(patch, layer.layer_mode, self.screen_width, self.screen_height)
                for patch in layer_patches
            ):
                first_visible = index

        for index, (layer, layer_patches, render_spent) in enumerate(rendered_layers):
            layer_name = layer.__class__.__name__
            rendered = time.perf_counter()
            if index < first_visible:
                continue

            with track_wait(f"layer_composite_{layer_name}", instrument):
                if layer_patches:
                    for patch in layer_patches:
                        composite_patch(
                            self.output_buffer,
                            patch,
                            layer.layer_mode,
                            self.screen_width,
                            self.screen_height,
                        )
            if self._timing_enabled:
                spent = self._timing.setdefault(layer_name, [0.0, 0.0])
                spent[0] += render_spent
                spent[1] += time.perf_counter() - rendered

        if self._timing_enabled:
            self._report_timing()
        return self.output_buffer

    def _report_timing(self) -> None:
        self._timing_frames += 1
        now = time.perf_counter()
        if now - self._timing_since < 5.0:
            return
        frames = max(self._timing_frames, 1)
        lines = sorted(self._timing.items(), key=lambda item: -sum(item[1]))
        report = ", ".join(
            f"{name} {render * 1000 / frames:.1f}+{comp * 1000 / frames:.1f}"
            for name, (render, comp) in lines
            if render + comp > 0.001 * frames
        )
        logging.info("Layer ms/frame (render+composite) over %d frames: %s", frames, report)
        self._timing, self._timing_frames, self._timing_since = {}, 0, now
