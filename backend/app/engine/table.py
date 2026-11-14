"""PLAN §4.6 — SlotTable memoizada y suavizado circular de fechas."""

from typing import Literal

import numpy as np
import pandas as pd

from app.data.crops import get_crop
from app.engine.calendar import get_hemisphere, get_sowing_grid, get_valid_seasons
from app.engine.slot import SlotSimulationResult, simulate_slot


class SlotTable:
    """PLAN §4.6 — Tabla memoizada de resultados de simulación de slots."""

    def __init__(
        self,
        weather_df: pd.DataFrame,
        lat: float,
        soil_texture: str,
        seasons: list[int] | None = None,
    ) -> None:
        self.weather_df = weather_df
        self.lat = lat
        self.soil_texture = soil_texture
        self.hemisphere = get_hemisphere(lat)
        self.seasons = seasons if seasons is not None else get_valid_seasons(self.hemisphere)
        self.sowing_grid = get_sowing_grid(self.hemisphere)
        self._cache: dict[tuple[str, int, str], SlotSimulationResult] = {}
        self.simulation_count: int = 0

    def get_grid_index(self, sow_date_str: str) -> int:
        """PLAN §4.1, §4.6 — Obtiene el índice (0..23) en la rejilla para una fecha 'MM-DD'."""
        return self.sowing_grid.index(sow_date_str)

    def get_slot_result(
        self,
        crop_id: str,
        grid_idx: int,
        prev_mode: Literal["fallow", "crop"] | str,
    ) -> SlotSimulationResult:
        """PLAN §4.6 — Simula o recupera de memo un slot por (cultivo, grid_idx, modo)."""
        n_grid = len(self.sowing_grid)
        grid_idx_norm = grid_idx % n_grid
        key = (crop_id, grid_idx_norm, prev_mode)

        if key not in self._cache:
            sow_date_str = self.sowing_grid[grid_idx_norm]
            crop = get_crop(crop_id)
            self.simulation_count += 1
            result = simulate_slot(
                crop=crop,
                sow_date_str=sow_date_str,
                prev_mode=prev_mode,
                soil_texture=self.soil_texture,
                weather_df=self.weather_df,
                lat=self.lat,
                seasons=self.seasons,
            )
            self._cache[key] = result

        return self._cache[key]

    def get_smoothed_y_rel(
        self,
        crop_id: str,
        grid_idx: int,
        prev_mode: Literal["fallow", "crop"] | str,
    ) -> np.ndarray:
        """PLAN §4.6 — Tabla suavizada: Ȳ[c,g,m] = media(Y[c,g-1,m], Y[c,g,m], Y[c,g+1,m]) circular."""
        n_grid = len(self.sowing_grid)
        idx_prev = (grid_idx - 1) % n_grid
        idx_curr = grid_idx % n_grid
        idx_next = (grid_idx + 1) % n_grid

        res_prev = self.get_slot_result(crop_id, idx_prev, prev_mode)
        res_curr = self.get_slot_result(crop_id, idx_curr, prev_mode)
        res_next = self.get_slot_result(crop_id, idx_next, prev_mode)

        return np.mean([res_prev.y_rel, res_curr.y_rel, res_next.y_rel], axis=0)
