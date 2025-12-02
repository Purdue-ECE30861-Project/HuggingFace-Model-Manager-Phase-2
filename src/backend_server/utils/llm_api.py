#!/usr/bin/env python3
"""
chat_prompt.py — Send a command-line prompt to OpenAI's ChatGPT API and print the response.

Usage:
    python llm_api.py

    https://genai.rcac.purdue.edu/

"""

import os
import requests


class LLMAccessor:
    def __init__(self, key: str):
        self.genai_key = key

    def make_prompt(self, token, role, content):
        url = "https://genai.rcac.purdue.edu/api/chat/completions"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        body = {
            "model": "llama3.1:latest",
            "messages": [{"role": role, "content": content}],
            "stream": False,
        }
        response = requests.post(url, headers=headers, json=body)
        if response.status_code == 200:
            return response.text
        else:
            raise Exception(f"Error: {response.status_code}, {response.text}")

    def main(self, text):
        api_key = self.genai_key
        if not api_key:
            raise RuntimeError("Missing GENAI_STUDIO_TOKEN environment variable")

        response = self.make_prompt(api_key, role="user", content=text)

        return response


if __name__ == "__main__":
    apiTester = LLMAccessor("mog this key")
    hfurl = "https://huggingface.co/google-bert/bert-base-uncased"
    prompt = "Given this link to a HuggingFace model repository, can you assess the Bus Factor of the model based on size of the organization/members \
                and likelihood that the work for developing this model was evenly split but all contributors. \
                I would like you to return a single value from 0-1 with 1 being perfect bus factor and no risk involved, and 0 being one singular contributor doing all the work. \
                This response should just be the 0-1 value with no other text given."

    print(apiTester.main(f"URL: {hfurl}, instructions: {prompt}"))

    # print(apiTester.main("Please give me a list of assessment areas that make good quality code"))
