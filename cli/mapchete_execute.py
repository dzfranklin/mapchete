#!/usr/bin/env python

import os
import sys
import argparse
import imp
import yaml
from functools import partial
from multiprocessing import Pool, cpu_count
from progressbar import ProgressBar

from mapchete import *
from tilematrix import TilePyramid, MetaTilePyramid
from tilematrix import *

def main(args):

    parser = argparse.ArgumentParser()
    parser.add_argument("mapchete_file", type=str)
    parser.add_argument("--zoom", "-z", type=int, nargs='*', )
    parser.add_argument("--bounds", "-b", type=float, nargs='*')
    parsed = parser.parse_args(args)

    try:
        config = get_clean_configuration(
            parsed.mapchete_file,
            zoom=parsed.zoom,
            bounds=parsed.bounds
            )
        base_tile_pyramid = TilePyramid(str(config["output_srs"]))
        tile_pyramid = MetaTilePyramid(base_tile_pyramid, config["metatiling"])
    except Exception as e:
        #sys.exit(e)
        raise

    # Determine tiles to be processed, depending on:
    # - zoom level and
    # - input files bounds OR user defined bounds
    work_tiles = []
    for zoom in config["zoom_levels"]:
        bbox = config["process_area"][zoom]
        if not bbox.is_empty:
            work_tiles.extend(tile_pyramid.tiles_from_geom(bbox, zoom))

    print len(work_tiles), "tiles to be processed"

    # # Prepare input process
    # process_name = os.path.splitext(os.path.basename(config["process_file"]))[0]
    # new_process = imp.load_source(
    #     process_name + "Process",
    #     config["process_file"]
    #     )
    # user_defined_process = new_process.Process(parsed.mapchete_file)
    # print "processing", user_defined_process.identifier
    f = partial(worker,
        # mapchete_process=user_defined_process,
        mapchete_file=parsed.mapchete_file,
        tile_pyramid=tile_pyramid,
        config=config
    )
    pool = Pool(cpu_count())
    log = ""

    try:
        counter = 0
        pbar = ProgressBar(maxval=len(work_tiles)).start()
        for output in pool.imap_unordered(f, work_tiles):
            counter += 1
            pbar.update(counter)
            if output:
                log += str(output) + "\n"
        pbar.finish()
    except:
        raise
    finally:
        pool.close()
        pool.join()

    print log


def worker(tile, mapchete_file, tile_pyramid, config):
    # Prepare input process
    process_name = os.path.splitext(os.path.basename(config["process_file"]))[0]
    new_process = imp.load_source(
        process_name + "Process",
        config["process_file"]
        )
    mapchete_process = new_process.Process(tile, tile_pyramid, mapchete_file)
    # print "processing", user_defined_process.identifier

    try:
        mapchete_process.execute(tile, tile_pyramid, config)
    except Exception as e:
        return tile, e
    finally:
        mapchete_process = None
    return tile, "ok"


if __name__ == "__main__":
    main(sys.argv[1:])
