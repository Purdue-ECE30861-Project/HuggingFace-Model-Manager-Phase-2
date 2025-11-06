



from dataclasses import dataclass
from src.utils.get_metadata import find_github_links
from src.classes.Metric import Metric
import time
from dotenv import load_dotenv
import requests
import re
import os
import json

github_pattern = re.compile(r"^(.*)?github.com\/([^\/]+)\/([^\/]+)\/?(.*)$")

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

@dataclass
class Reviewedness(Metric):
    # TODO: Rebalance weights
    def __init__(self, metricName: str = "License", metricWeighting: float = 0.0):
        super().__init__(metricName, 0, metricWeighting)
    
    def evaluate(self, url: str, githubURL: str|None) -> tuple[float, int]:
        """
        Evaluates the percentage of code which was introduced through pull
        request and the time it took to run the evaluation.
        
        :param url: model URL
        :param githubURL: Associated github URL (if present)
        """
        load_dotenv()
        t0 = time.perf_counter_ns()
        if githubURL is None:
            links = list(find_github_links(url))
        else:
            links = [githubURL]
        if len(links) == 0:
            return -1.0, t0

        pr_additions = 0
        pr_deletions = 0
        commit_additions = 0
        commit_deletions = 0
        for link in links:
            next_page = True
            index: str|None = None
            while next_page:
                result = self._execute_query(graphql_query_get_merge_additions, link, index)
                new_pr_ad, new_pr_del, new_com_add, new_com_del, index = self._parse_response(result)
                pr_additions += new_pr_ad
                pr_deletions += new_pr_del
                commit_additions += new_com_add
                commit_deletions += new_com_del
                if index is None:
                    next_page = False
        total = pr_additions + pr_deletions + commit_additions +commit_deletions
        return (pr_additions + pr_deletions)/total, t0
    
    def _parse_response(self, response: requests.Response) -> tuple[int, int, int, int, str|None]:
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
            commit_history = response_obj["data"]["repository"]["defaultBranchRef"]["target"]["history"]
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

    def _execute_query(self, query: str, link: str, index: str|None) -> requests.Response:
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
            json = {"query": query % (name, owner, f", after: {index}")}
        else:
            json = {"query": query % (name, owner, "")}
        headers = {"Authorization": f"bearer {os.getenv('GITHUB_TOKEN')}"}
        return requests.post(url=url, json=json, headers=headers)