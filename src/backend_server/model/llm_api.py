#!/usr/bin/env python3
"""
chat_prompt.py — Send a command-line prompt to OpenAI's ChatGPT API and print the response.

Usage:
    python llm_api.py

    https://genai.rcac.purdue.edu/

"""

import requests
import boto3
import json

class LLMAccessor:
    def __init__(self, key: str|None, bedrock: bool, model_name: str|None = None):
        if bedrock and model_name == None:
            raise ValueError("using bedrock with no model name is not supported")
        if not key and not bedrock:
            raise ValueError("using GenAI studio without a key is unsupported")
        self.genai_key = key
        self.bedrock = bedrock
        self.model_name = model_name
        

    def make_studio_prompt(self, token: str, role: str, content: str):
        url = "https://genai.rcac.purdue.edu/api/chat/completions"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        body = { # type: ignore
            "model": "llama3.1:latest",
            "messages": [{"role": role, "content": content}],
            "stream": False,
        }
        response = requests.post(url, headers=headers, json=body) # type: ignore
        if response.status_code == 200:
            response_data = json.loads(response.text)
            response_data  = response_data["choices"][0]["message"]["content"]
            return response_data
        else:
            raise Exception(f"Error: {response.status_code}, {response.text}")
    
    def make_bedrock_prompt(self, prompt: str) -> str:
        llm_api = boto3.client("bedrock-runtime", region="us-east-2")
        conversation = [
            {
                "role": "user",
                "content": [{"text": prompt}]
            }
        ]
        config = {"maxTokens": 512, "temperature": 0.5, "topP": 0.9}
        request = llm_api.converse(modelId=self.model_name, messages=conversation, inferenceConfig=config)
        return request['output']["message"]["content"][0]["text"]

    def main(self, text: str):
        if not self.bedrock:
            api_key = self.genai_key
            if not api_key:
                raise RuntimeError("Missing GENAI_STUDIO_TOKEN environment variable")

            response = self.make_studio_prompt(api_key, role="user", content=text)

            return response
        else:
            response = self.make_bedrock_prompt(text)
            return response
            


if __name__ == "__main__":
    apiTester = LLMAccessor(None, bedrock=True, model_name="us.anthropic.claude-3-haiku-20240307-v1:0")
    hfurl = "https://huggingface.co/google-bert/bert-base-uncased"
    prompt = "Given this link to a HuggingFace model repository, can you assess the Bus Factor of the model based on size of the organization/members \
                and likelihood that the work for developing this model was evenly split but all contributors. \
                I would like you to return a single value from 0-1 with 1 being perfect bus factor and no risk involved, and 0 being one singular contributor doing all the work. \
                This response should just be the 0-1 value with no other text given."

    print(apiTester.main(f"URL: {hfurl}, instructions: {prompt}"))

    # print(apiTester.main("Please give me a list of assessment areas that make good quality code"))
