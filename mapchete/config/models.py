from typing import List, Optional, Type, Union

from distributed import Client
from pydantic import BaseModel, NonNegativeInt, field_validator
from shapely.geometry.base import BaseGeometry

from mapchete.types import Bounds, BoundsLike, MPathLike, ZoomLevels, ZoomLevelsLike


class OutputConfigBase(BaseModel):
    format: str
    metatiling: Optional[int] = 1
    pixelbuffer: Optional[NonNegativeInt] = 0

    @field_validator("metatiling", mode="before")
    def _metatiling(cls, value: int) -> int:  # pragma: no cover
        _metatiling_opts = [2**x for x in range(10)]
        if value not in _metatiling_opts:
            raise ValueError(f"metatling must be one of {_metatiling_opts}")
        return value


class PyramidConfig(BaseModel):
    grid: Union[str, dict]
    metatiling: Optional[int] = 1
    pixelbuffer: Optional[NonNegativeInt] = 0

    @field_validator("metatiling", mode="before")
    def _metatiling(cls, value: int) -> int:  # pragma: no cover
        _metatiling_opts = [2**x for x in range(10)]
        if value not in _metatiling_opts:
            raise ValueError(f"metatling must be one of {_metatiling_opts}")
        return value


class ProcessConfig(BaseModel, arbitrary_types_allowed=True):
    pyramid: PyramidConfig
    output: dict
    zoom_levels: Union[ZoomLevels, ZoomLevelsLike]
    process: Optional[Union[MPathLike, List[str]]] = None
    baselevels: Optional[dict] = None
    input: Optional[dict] = None
    config_dir: Optional[MPathLike] = None
    mapchete_file: Optional[MPathLike] = None
    area: Optional[Union[MPathLike, BaseGeometry]] = None
    area_crs: Optional[Union[dict, str]] = None
    bounds: Optional[Union[Bounds, BoundsLike]] = None
    bounds_crs: Optional[Union[dict, str]] = None
    process_parameters: Optional[dict] = None


class DaskSettings(BaseModel):
    process_graph: bool = True
    max_submitted_tasks: int = 500
    chunksize: int = 100
    scheduler: Optional[str] = None
    client: Optional[Type[Client]] = None
