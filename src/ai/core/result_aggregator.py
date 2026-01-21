# -*- coding: utf-8 -*-
"""Result aggregator for summarizing agent outcomes."""

from typing import List, Dict, Any
from .models import AgentResponse


class ResultAggregator:
    def aggregate(self, responses: List[AgentResponse]) -> Dict[str, Any]:
        success = [r for r in responses if r.status == "success"]
        failure = [r for r in responses if r.status == "failure"]
        return {
            "success_count": len(success),
            "failure_count": len(failure),
            "success_responses": success,
            "failure_responses": failure,
            "all_output_files": [f for r in success for f in (r.output_files or [])],
        }
