from pathlib import Path
from src.contracts.artifact_contracts import Artifact
from src.contracts.metric_std import MetricStd
import logging


logger = logging.getLogger(__name__)


class TreeScore(MetricStd[float]):
    metric_name = "tree_score"


    def calculate_metric_score(self, ingested_path: Path, artifact_data: Artifact, *args, **kwargs) -> float:
        try:
            lineage_graph = kwargs.get('lineage_graph')
            db_accessor = kwargs.get('db_accessor')


            if not lineage_graph or not db_accessor:
                logger.warning("Lineage graph or DB accessor not provided.")
                return 0.0
           
            model_id = artifact_data.metadata.id    # filepath/model-name
            model_url = artifact_data.data.url      #HF URL


            logger.debug(f"Calculating Treescore for model: {model_id}")


            lineage_dict = lineage_graph.get_lineage_dict(model_url, depth = 1)


            parent_ids = set()
            for edge in lineage_dict.get("edges", []):
                if edge["to_node_artifact_id"] == model_id:
                    parent_ids.add(edge["from_node_artifact_id"])


            if not parent_ids:
                logger.debug(f"Treescore: No parents found for {model_id}")
                return 0.0
           
            logger.debug(f"Treescore: Found {len(parent_ids)} parent(s) for {model_id}: {parent_ids}")


            parent_scores = []
            for parent_id in parent_ids:
                artifacts = db_accessor.get_by_name(parent_id)


                if artifacts and len(artifacts) > 0:
                    parent_net_score = artifacts[0].rating.net_score
                    parent_scores.append(parent_net_score)
                    logger.debug(f"Treescore: parent'{parent_id}' net_score = {parent_net_score:.3f}")
                else:
                    logger.debug(f"Treescore: Parent '{parent_id}' not found in registry")


            if parent_scores:
                treescore = sum(parent_scores) / len(parent_scores)
                logger.info(f"Treescore for model '{model_id}': {treescore:.3f}")
                return treescore
            else:
                logger.debug(f"parents exist in lineage but none in registry for {model_id}")
                logger.debug(f"found {len(parent_ids)} in lineage")
                return 0.0
       
        except Exception as e:
            logger.error(f"Error calculating Treescore for '{artifact_data.metadata.id}': {e}", exc_info = True)
            return 0.0