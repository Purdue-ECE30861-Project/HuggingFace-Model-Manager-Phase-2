import logging
from pathlib import Path

from typing_extensions import override

from src.backend_server.model.dependencies import DependencyBundle
from src.contracts.artifact_contracts import Artifact, ArtifactLineageGraph
from src.contracts.metric_std import MetricStd
from src.contracts.model_rating import ModelRating

logger = logging.getLogger(__name__)


class DBManager:
    pass
class TreeScore(MetricStd[float]):
    metric_name = "tree_score"

    @override
    def calculate_metric_score(self, ingested_path: Path, artifact_data: Artifact, dependency_bundle: DependencyBundle, *args, **kwargs) -> float:
        try:
            lineage_graph: ArtifactLineageGraph|None = dependency_bundle.db.router_lineage.db_artifact_lineage(artifact_data.metadata.id)

            if not lineage_graph:
                logger.warning("Error retrieving lineage graph")
                return 0.0
           
            model_id: str = artifact_data.metadata.id    # filepath/model-name

            logger.debug(f"Calculating Treescore for model: {model_id}")

            net_rating: float = 0.0
            net_rating_max: float = 0.0

            for node in lineage_graph.nodes:
                rating: ModelRating|None = dependency_bundle.db.router_rating.db_rating_get(node.artifact_id)
                if rating:
                    net_rating_max += 1.0
                    net_rating += rating.net_score

            if net_rating_max > 0:
                return net_rating / net_rating_max
            return 0.0

        except Exception as e:
            logger.error(f"Error calculating Treescore for '{artifact_data.metadata.id}': {e}", exc_info = True)
            return 0.0