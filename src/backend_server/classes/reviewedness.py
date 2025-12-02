import json
import logging
import re
from pathlib import Path
from typing import override

import requests

import src.backend_server.utils.get_metadata
from src.backend_server.model.dependencies import DependencyBundle
from src.contracts.artifact_contracts import Artifact
from src.contracts.metric_std import MetricStd
from src.backend_server.global_state import DBManager
from src.backend_server.global_state import global_config


github_pattern = re.compile(r"^(.*)?github.com\/([^\/]+)\/([^\/]+)\/?(.*)$")

logger = logging.getLogger(__name__)

graphql_query_get_merge_additions = """
{
  repository(name: "%s", owner: "%s") {
    defaultBranchRef {
      target {
        ... on Commit {
          history(first: 100%s) {
            edges {
              node {
                additions
                deletions
                associatedPullRequests(first: 1) {
                  totalCount
                }
              }
            }
            pageInfo{
              hasNextPage
              endCursor
            }
          }
        }
      }
    }
  }
}
"""


class Reviewedness(MetricStd):
    # TODO: Rebalance weights
    def __init__(self, metricName: str = "License", metricWeighting: float = 0.0):
        super().__init__(metricWeighting)

    @override
    def calculate_metric_score(
        self,
        ingested_path: Path,
        artifact_data: Artifact,
        dependency_bundle: DependencyBundle,
        *args,
        **kwargs,
    ) -> float:
        attached_codebase_info: None | list[Artifact] = (
            dependency_bundle.db.router_lineage.db_artifact_get_attached_codebases(
                artifact_data.metadata.id
            )
        )
        if attached_codebase_info is None:
            logger.error("No datasets attached for metric score")
            return 0.0
        max_score: float = float(len(attached_codebase_info))
        current_score: float = 0.0

        for codebase in attached_codebase_info:
            current_score += self.evaluate(artifact_data.data.url, codebase.data.url)

        return current_score / max_score

    def evaluate(self, url: str, githubURL: str | None) -> float:
        """
        Evaluates the percentage of code which was introduced through pull
        request and the time it took to run the evaluation.

        :param url: model URL
        :param githubURL: Associated github URL (if present)
        """
        if githubURL is None:
            links = list(src.backend_server.utils.get_metadata.find_github_links(url))
        else:
            links = [githubURL]
        if len(links) == 0 or githubURL is None:
            return -1.0

        pr_additions = 0
        pr_deletions = 0
        commit_additions = 0
        commit_deletions = 0
        for link in links:
            next_page = True
            index: str | None = None
            while next_page:
                result = self._execute_query(
                    graphql_query_get_merge_additions, link, index
                )
                new_pr_ad, new_pr_del, new_com_add, new_com_del, index = (
                    self._parse_response(result)
                )
                pr_additions += new_pr_ad
                pr_deletions += new_pr_del
                commit_additions += new_com_add
                commit_deletions += new_com_del
                if index is None:
                    next_page = False
        total = pr_additions + pr_deletions + commit_additions + commit_deletions
        if total == 0:
            return 0
        return (pr_additions + pr_deletions) / total

    def _parse_response(
        self, response: requests.Response
    ) -> tuple[int, int, int, int, str | None]:
        """
        gets all additions and deletions done in and out of pull requests, in that order
        :param response: the GraphQL response of the query
        """
        pr_additions = 0
        pr_deletions = 0
        commit_additions = 0
        commit_deletions = 0
        next_cur = ""
        response_obj = json.loads(response.text)
        try:
            commit_history = response_obj["data"]["repository"]["defaultBranchRef"][
                "target"
            ]["history"]
            for commit in commit_history["edges"]:
                commit = commit["node"]
                if commit["associatedPullRequests"]["totalCount"] > 0:
                    pr_additions += commit["additions"]
                    pr_deletions += commit["deletions"]
                else:
                    commit_additions += commit["additions"]
                    commit_deletions += commit["deletions"]
            if commit_history["pageInfo"]["hasNextPage"]:
                next_cur = commit_history["pageInfo"]["endCursor"]
            else:
                next_cur = None
        except KeyError:
            raise ValueError("Invalid GraphQL query or Github URL")
        return pr_additions, pr_deletions, commit_additions, commit_deletions, next_cur

    def _execute_query(
        self, query: str, link: str, index: str | None
    ) -> requests.Response:
        """
        executes a given graphql query.

        :param query: the query to execute
        :param link: the url of the repository to query
        :param index: the pagination index for the query
        """
        matches = github_pattern.match(link)
        if matches is None:
            raise ValueError("invalid GitHub URL")

        owner = matches.group(2)
        name = matches.group(3)

        if not isinstance(owner, str) or not isinstance(name, str):
            raise ValueError("invalid Github URL")
        url = "https://api.github.com/graphql"
        if index is not None:
            json = {"query": query % (name, owner, f', after: "{index}"')}
        else:
            json = {"query": query % (name, owner, "")}
        headers = {"Authorization": f"bearer {global_config.github_pat}"}
        return requests.post(url=url, json=json, headers=headers)
