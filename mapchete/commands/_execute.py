"""Execute a process."""
import logging
from contextlib import AbstractContextManager
from multiprocessing import cpu_count
from typing import List, Optional, Tuple, Type, Union

from rasterio.crs import CRS
from shapely.geometry.base import BaseGeometry

import mapchete
from mapchete.commands.observer import ObserverProtocol, Observers
from mapchete.config.parse import bounds_from_opts, raw_conf, raw_conf_process_pyramid
from mapchete.enums import Concurrency, ProcessingMode, Status
from mapchete.errors import JobCancelledError
from mapchete.executor import Executor
from mapchete.processing.types import TaskResult
from mapchete.types import Progress

logger = logging.getLogger(__name__)


def execute(
    mapchete_config: Union[str, dict],
    zoom: Union[int, List[int]] = None,
    area: Union[BaseGeometry, str, dict] = None,
    area_crs: Union[CRS, str] = None,
    bounds: Tuple[float] = None,
    bounds_crs: Union[CRS, str] = None,
    point: Tuple[float, float] = None,
    point_crs: Tuple[float, float] = None,
    tile: Tuple[int, int, int] = None,
    overwrite: bool = False,
    mode: ProcessingMode = ProcessingMode.CONTINUE,
    concurrency: Concurrency = Concurrency.processes,
    workers: int = None,
    multiprocessing_start_method: str = None,
    dask_scheduler: str = None,
    dask_max_submitted_tasks=1000,
    dask_chunksize=100,
    dask_client=None,
    dask_compute_graph=True,
    dask_propagate_results=True,
    executor_getter: AbstractContextManager = Executor,
    profiling: bool = False,
    observers: Optional[List[ObserverProtocol]] = None,
    retry_on_exception: Tuple[Type[Exception], Type[Exception]] = Exception,
    cancel_on_exception: Type[Exception] = JobCancelledError,
    retries: int = 0,
    **kwargs,
):
    """
    Execute a Mapchete process.

    Parameters
    ----------
    mapchete_config : str or dict
        Mapchete configuration as file path or dictionary.
    zoom : integer or list of integers
        Single zoom, minimum and maximum zoom or a list of zoom levels.
    area : str, dict, BaseGeometry
        Geometry to override bounds or area provided in process configuration. Can be either a
        WKT string, a GeoJSON mapping, a shapely geometry or a path to a Fiona-readable file.
    area_crs : CRS or str
        CRS of area (default: process CRS).
    bounds : tuple
        Override bounds or area provided in process configuration.
    bounds_crs : CRS or str
        CRS of area (default: process CRS).
    point : iterable
        X and y coordinates of point whose corresponding process tile bounds will be used.
    point_crs : str or CRS
        CRS of point (defaults to process pyramid CRS).
    tile : tuple
        Zoom, row and column of tile to be processed (cannot be used with zoom)
    overwrite : bool
        Overwrite existing output.
    mode : str
        Set process mode. One of "readonly", "continue" or "overwrite".
    workers : int
        Number of execution workers when processing concurrently.
    multiprocessing_start_method : str
        Method used by multiprocessing module to start child workers. Availability of methods
        depends on OS.
    concurrency : str
        Concurrency to be used. Could either be "processes", "threads" or "dask".
    dask_scheduler : str
        URL to dask scheduler if required.
    dask_max_submitted_tasks : int
        Make sure that not more tasks are submitted to dask scheduler at once. (default: 500)
    dask_chunksize : int
        Number of tasks submitted to the scheduler at once. (default: 100)
    dask_client : dask.distributed.Client
        Reusable Client instance if required. Otherwise a new client will be created.
    dask_compute_graph : bool
        Build and compute dask graph instead of submitting tasks as preprocessing & zoom tiles
        batches. (default: True)
    dask_propagate_results : bool
        Propagate results between tasks. This helps to minimize read calls when building overviews
        but can lead to a much higher memory consumption on the cluster. Only with effect if
        dask_compute_graph is activated. (default: True)
    """
    print_task_details = True
    mode = "overwrite" if overwrite else mode
    all_observers = Observers(observers)

    if not isinstance(retry_on_exception, tuple):
        retry_on_exception = (retry_on_exception,)
    workers = workers or cpu_count()

    all_observers.notify(status=Status.parsing)

    if tile:
        tile = raw_conf_process_pyramid(raw_conf(mapchete_config)).tile(*tile)
        bounds = tile.bounds
        zoom = tile.zoom
    else:
        bounds = bounds_from_opts(
            point=point,
            point_crs=point_crs,
            bounds=bounds,
            bounds_crs=bounds_crs,
            raw_conf=raw_conf(mapchete_config),
        )

    # be careful opening mapchete not as context manager
    with mapchete.open(
        mapchete_config,
        mode=mode,
        bounds=bounds,
        zoom=zoom,
        area=area,
        area_crs=area_crs,
    ) as mp:
        attempt = 0

        # the part below can be retried n times #
        #########################################

        while retries + 1:
            attempt += 1

            # simulating that with every retry, probably less tasks have to be
            # executed
            if attempt > 1:
                retries_str = "retry" if retries == 1 else "retries"
                all_observers.notify(
                    message=f"attempt {attempt}, {retries} {retries_str} left"
                )

            # simulating how long it takes to determine which outputs have to be
            # processed
            all_observers.notify(status=Status.initializing)
            # determine tasks
            preprocessing_tasks = mp.config.preprocessing_tasks_count()
            tiles_tasks = 1 if tile else mp.count_tiles()
            total_tasks = preprocessing_tasks + tiles_tasks
            all_observers.notify(
                message=f"processing {preprocessing_tasks} preprocessing tasks and {tiles_tasks} tile tasks on {workers} worker(s)"
            )
            if total_tasks == 0:
                all_observers.notify(status=Status.done)
                return

            # automatically use dask Executor if dask scheduler is defined
            if dask_scheduler or dask_client or concurrency == "dask":
                concurrency = "dask"
            # use sequential Executor if only one tile or only one worker is defined
            elif total_tasks == 1 or workers == 1:
                logger.debug(
                    "using sequential Executor because there is only one %s",
                    "task" if total_tasks == 1 else "worker",
                )
                concurrency = None
            all_observers.notify(message="waiting for executor ...")

            with executor_getter(
                concurrency=concurrency,
                dask_scheduler=dask_scheduler,
                dask_client=dask_client,
                multiprocessing_start_method=multiprocessing_start_method,
                max_workers=workers,
            ) as executor:
                # run
                all_observers.notify(
                    status=Status.running,
                    progress=Progress(total=total_tasks),
                    message=f"sending {total_tasks} tasks to {executor} ...",
                )
                try:
                    for ii, future in enumerate(
                        mp.compute(
                            tile=tile,
                            workers=workers,
                            zoom=None if tile else zoom,
                            dask_max_submitted_tasks=dask_max_submitted_tasks,
                            dask_chunksize=dask_chunksize,
                            dask_compute_graph=dask_compute_graph,
                            dask_propagate_results=dask_propagate_results,
                            profiling=profiling,
                        ),
                        1,
                    ):
                        result = TaskResult.from_future(future)
                        if print_task_details:
                            msg = f"task {result.id}: {result.process_msg}"
                            if result.profiling:  # pragma: no cover
                                max_allocated = (
                                    result.profiling["memory"].max_allocated
                                    / 1024
                                    / 1024
                                )
                                head_requests = result.profiling["requests"].head_count
                                get_requests = result.profiling["requests"].get_count
                                requests = head_requests + get_requests
                                transfer = (
                                    result.profiling["requests"].get_bytes / 1024 / 1024
                                )
                                msg += f" (max memory usage: {max_allocated:.2f}MB, {requests} GET and HEAD requests, {transfer:.2f}MB transferred)"
                            all_observers.notify(message=msg)
                        all_observers.notify(
                            progress=Progress(total=total_tasks, current=ii),
                            task_result=result,
                        )
                    return

                except cancel_on_exception:
                    all_observers.notify(status=Status.cancelled)
                    raise

                except retry_on_exception:
                    all_observers.notify(
                        status=Status.failed,
                    )
                    if retries:
                        retries -= 1
                        all_observers.notify(status=Status.retrying)
                    else:
                        raise
