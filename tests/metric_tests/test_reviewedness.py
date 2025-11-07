from src.classes.Reviewedness import Reviewedness
from unittest import TestCase
from unittest.mock import patch, Mock
from typing import Any
import re

class FakeResponse:
    def __init__(self, text: str):
        self.text = text


class TestReviewednessMetric(TestCase):
    @patch("requests.post")
    def testScoringLogic(self, mock_post: Mock):
        res = FakeResponse(
            """
    {
  "data": {
    "repository": {
      "defaultBranchRef": {
        "target": {
          "history": {
            "edges": [
              {
                "node": {
                  "additions": 20,
                  "deletions": 10,
                  "associatedPullRequests": {
                    "totalCount": 0
                  }
                }
              },
              {
                "node": {
                  "additions": 40,
                  "deletions": 40,
                  "associatedPullRequests": {
                    "totalCount": 1
                  }
                }
              },
              {
                "node": {
                  "additions": 30,
                  "deletions": 10,
                  "associatedPullRequests": {
                    "totalCount": 1
                  }
                }
              }
            ],
            "pageInfo": {
              "hasNextPage": false,
              "endCursor": ""
            }
          }
        }
      }
    }
  }
}
"""
        )
        mock_post.return_value = res
        metric = Reviewedness()
        res, _ = metric.evaluate(url="", githubURL="https://github.com/x/x")
        self.assertAlmostEqual(res, 120 / 150)

    @patch("requests.post")
    def testPagination(self, mock_post: Mock):
        p1 = FakeResponse(
            """
    {
  "data": {
    "repository": {
      "defaultBranchRef": {
        "target": {
          "history": {
            "edges": [
              {
                "node": {
                  "additions": 20,
                  "deletions": 10,
                  "associatedPullRequests": {
                    "totalCount": 0
                  }
                }
              },
              {
                "node": {
                  "additions": 40,
                  "deletions": 40,
                  "associatedPullRequests": {
                    "totalCount": 1
                  }
                }
              },
              {
                "node": {
                  "additions": 30,
                  "deletions": 10,
                  "associatedPullRequests": {
                    "totalCount": 1
                  }
                }
              }
            ],
            "pageInfo": {
              "hasNextPage": true,
              "endCursor": "weird looking th1ng9do00d+1e"
            }
          }
        }
      }
    }
  }
}
"""
        )
        p2 =  FakeResponse(
            """
    {
  "data": {
    "repository": {
      "defaultBranchRef": {
        "target": {
          "history": {
            "edges": [
              {
                "node": {
                  "additions": 60,
                  "deletions": 10,
                  "associatedPullRequests": {
                    "totalCount": 0
                  }
                }
              }
            ],
            "pageInfo": {
              "hasNextPage": false,
              "endCursor": ""
            }
          }
        }
      }
    }
  }
}
"""
        )
        def paginated_response(url: str, json: Any|None, headers: dict[str, str])->FakeResponse:
            if json is None:
                raise ValueError("no graphql query given")
            request = json["query"]
            match = re.search(r", after: \"(.*)\"", request)
            if match is None:
                return p1
            elif match.group(1) == "weird looking th1ng9do00d+1e":
                return p2
            else:
                raise ValueError("invalid cursor given")
        
        mock_post.side_effect = paginated_response
        
        metric = Reviewedness()
        res, _ = metric.evaluate(url="", githubURL="https://github.com/x/x")
        self.assertAlmostEqual(res, 120 / 220)

    @patch("src.utils.get_metadata.find_github_links")
    def test_no_github_link(self, github_link_mock: Mock):
        ret: set[str] = set()
        github_link_mock.return_value = ret
        metric = Reviewedness()
        res, _ = metric.evaluate(url="https://huggingface.co/x/x", githubURL=None)
        self.assertEqual(res, -1)
        github_link_mock.assert_called()