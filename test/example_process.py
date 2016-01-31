#!/usr/bin/env python

from mapchete import MapcheteProcess, read_raster

"""
To initialize, the user has to provide:
 - execute(): implement process
 - mapchete_file: a .mapchete file
optional:
 - identifier
 - title
 - version
 - abstract

If the process gets executed, it only runs at a certain zoom level.
"""

import time

class Process(MapcheteProcess):
    """
    Main process class which inherits from MapcheteProcess.
    """
    def __init__(self, tile, tile_pyramid, config_path):
        MapcheteProcess.__init__(self, config_path)
        self.identifier = "example_process"
        self.title = "example process file",
        self.version = "dirty pre-alpha",
        self.abstract = "used for testing"
        self.tile = tile
        self.tile_pyramid = tile_pyramid

    def execute(self, tile, tile_pyramid, params):
        """
        Here, the magic shall happen.
        # print tile_pyramid.tile_bounds(*tile)
        # time.sleep(0.1)
        """
        zoom, col, row = tile
        if col % 2 == 1:
            raise IOError("some error")
        input_file = params["input_files"][zoom]['file2']
        read_raster(self, input_file)
