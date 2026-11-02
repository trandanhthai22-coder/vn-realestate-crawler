from bdscrawler.pipelines.apartment import ApartmentPipeline
from bdscrawler.pipelines.base import Pipeline
from bdscrawler.pipelines.detail import DetailPipeline
from bdscrawler.pipelines.lowrise import LowrisePipeline

PIPELINES: dict[str, type[Pipeline]] = {
    "apartment": ApartmentPipeline,
    "lowrise": LowrisePipeline,
    "detail": DetailPipeline,
}

__all__ = ["PIPELINES", "Pipeline", "ApartmentPipeline", "LowrisePipeline", "DetailPipeline"]
