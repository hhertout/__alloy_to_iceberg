""" from typing import Protocol

import polars as pl


class Processor(Protocol):
    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        ...
 """