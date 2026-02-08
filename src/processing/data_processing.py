import polars as pl

class Processor:
    @staticmethod
    def process(df: pl.DataFrame) -> pl.DataFrame:
        """Processes the DataFrame and returns a new DataFrame."""
        # Example processing: add a new column that is the sum of all numeric columns
        df = Processor.__remove_nans(df)
        df = Processor.__remove_nulls(df)
        return df
    
    @staticmethod
    def __remove_nans(df: pl.DataFrame) -> pl.DataFrame:
        """Removes rows with NaN values."""
        return df.drop_nans()

    @staticmethod
    def __remove_nulls(df: pl.DataFrame) -> pl.DataFrame:
        """Removes rows with null values."""
        return df