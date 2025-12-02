import logging
import re
import json
from typing import Optional
from enum import Enum
import requests
from src.backend_server.utils.llm_api import LLMAccessor

logger = logging.getLogger(__name__)


class LicenseCompatibility(str, Enum):
    """
    Compatibility assessment results.
    """
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    UNCERTAIN = "uncertain"
    ERROR = "error"

class LicenseChecker:
    
    def __init__(self, hf_token: Optional[str] = None, github_token: Optional[str] = None):
        self.hf_token = hf_token
        self.github_token = github_token
        self.session = requests.Session()
        self.llm_api = LLMAccessor()
        
        if github_token:
            self.session.headers.update({"Authorization": f"token {github_token}"})
    
    def normalize_license(self, license_str: str) -> str:
        """
        Normalize license string to canonical form.   
        """
        if not license_str:
            return "unknown"
        
        # Remove common prefixes/suffixes
        cleaned = re.sub(r"\(.*?\)", "", license_str).strip().lower()
        cleaned = cleaned.replace("_", "-").replace(" ", "-")
        cleaned = re.sub(r"-+", "-", cleaned)
        
        return cleaned
    
    def fetch_model_license(self, model_url: str) -> Optional[str]:
        """
        Fetch license from HuggingFace model.
        """
        try:
            # Extract model ID from URL
            parts = model_url.rstrip("/").split("/")
            if "huggingface.co" in model_url:
                model_id = "/".join(parts[-2:])
            else:
                model_id = model_url
            
            # Fetch model info from HF API
            api_url = f"https://huggingface.co/api/models/{model_id}"
            headers = {}
            if self.hf_token:
                headers["Authorization"] = f"Bearer {self.hf_token}"
            
            response = self.session.get(api_url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            license_id = None
            
            # Try cardData.license first
            if "cardData" in data and "license" in data["cardData"]:
                license_id = data["cardData"]["license"]
            
            # Try tags if cardData didn't work
            if not license_id and "tags" in data:
                for tag in data["tags"]:
                    if tag.startswith("license:"):
                        license_id = tag.replace("license:", "")
                        break
            
            if not license_id:
                logger.warning(f"No license found for model {model_id}")
                return None
            
            return license_id
            
        except Exception as e:
            logger.warning(f"Error fetching model license: {e}")
            return None
    
    def fetch_github_license(self, github_url: str) -> Optional[str]:
        """
        Fetch license from GitHub repository.
        """
        try:
            # Extract owner/repo from URL
            parts = github_url.rstrip("/").replace(".git", "").split("/")
            owner_repo = "/".join(parts[-2:])
            
            # Fetch repo info from GitHub API
            api_url = f"https://api.github.com/repos/{owner_repo}"
            
            response = self.session.get(api_url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            license_id = None
            
            # Get license from API
            if "license" in data and data["license"]:
                license_data = data["license"]
                if "spdx_id" in license_data and license_data["spdx_id"] != "NOASSERTION":
                    license_id = license_data["spdx_id"].lower()
                elif "key" in license_data:
                    license_id = license_data["key"]
            
            if not license_id:
                logger.warning(f"No license found for GitHub repo {owner_repo}")
                return None
            
            return license_id
            
        except Exception as e:
            logger.warning(f"Error fetching GitHub license: {e}")
            return None
    
    def assess_compatibility(
        self,
        model_license_id: str,
        code_license_id: str
    ) -> LicenseCompatibility:
        """
        Use LLM to assess license compatibility between model and code.
        """
        # Construct detailed prompt for LLM
        prompt = (f"""You are an expert in software licensing and machine learning model licenses. 

Analyze the compatibility between these two licenses for the specified use case:

MODEL LICENSE: {model_license_id}

CODE LICENSE: {code_license_id}

USAGE CONTEXT:
- fine_tuning_and_inference: Using the code to fine-tune the model AND using the fine-tuned model for inference/generation
- fine_tuning: Only using the code to fine-tune the model
- inference: Only using the code to perform inference with the model

IMPORTANT CONSIDERATIONS:
1. Fine-tuning typically creates a derivative work of the model
2. Strong copyleft licenses (GPL, AGPL) may require derivatives to use the same license
3. Permissive licenses (MIT, Apache, BSD) are generally compatible with most uses
4. ML-specific licenses (OpenRAIL, Llama) have special terms for responsible AI use
5. Non-commercial licenses (CC-BY-NC) prohibit commercial use
6. Some licenses prohibit modifications (CC-BY-ND)

TASK:
Assess whether these licenses are compatible for the stated usage. Consider:
- Can the code be used to fine-tune the model?
- Can the resulting fine-tuned model be used for inference?
- Are there any license conflicts or restrictions?
- What are the requirements for attribution, distribution, or share-alike?

Respond ONLY with a JSON object like:
{"{"}"compatible": true/false, "confidence": "high/medium/low"{"}"}.

Do NOT use code fences. Do NOT add explanation. Output JSON ONLY.""")
        try:
            # Call LLM API
            logger.debug(f"Calling LLM for license compatibility assessment")
            response = self.llm_api.main(prompt)
            
            # Parse LLM response
            try:
                if isinstance(response, str):
                    response_data = json.loads(response)
                    response_data  = json.loads(response_data["choices"][0]["message"]["content"])
                else:
                    response_data = response
                    
                logger.debug(f"LLM API response structure: {type(response_data)}")
                
                if isinstance(response_data, dict):
                    
                    is_compatible = response_data.get("compatible", False)
                    confidence = response_data.get("confidence", "low")
                else:
                    logger.warning(f"Unexpected LLM response format: {response_data}")
                    return LicenseCompatibility.UNCERTAIN

                logger.debug(f"Parsed LLM license assessment")       
                logger.info(f"LLM Assessment - Compatible: {is_compatible}, Confidence: {confidence}")
                
                # Determine status based on compatibility and confidence
                if is_compatible:
                    if confidence == "high":
                        status = LicenseCompatibility.COMPATIBLE
                    else:
                        status = LicenseCompatibility.UNCERTAIN
                else:
                    if confidence in ["high", "medium"]:
                        status = LicenseCompatibility.INCOMPATIBLE
                    else:
                        status = LicenseCompatibility.UNCERTAIN
                
                return status
                
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse LLM JSON response: {e}")
                logger.debug(f"Raw response: {response}")
                
            
        except Exception as e:
            logger.warning(f"Error calling LLM for license assessment: {e}")
            return (LicenseCompatibility.ERROR)
    
    def check_compatibility(
        self,
        model_url: str,
        github_url: str
    ) -> bool:
        """
        Check license compatibility between model and GitHub project using LLM.
            
        Returns:
            bool: True if compatible, False otherwise
        """
        try:
            # Fetch licenses
            model_license_id = self.fetch_model_license(model_url)
            code_license_id = self.fetch_github_license(github_url)
            
            if not model_license_id:
                return False
            
            if not code_license_id:
                return False
            
            # Use LLM to assess compatibility
            logger.info(f"Assessing compatibility between {model_license_id} and {code_license_id} using LLM")
            status = self.assess_compatibility(
                model_license_id,
                code_license_id
            )
            
            return (status == LicenseCompatibility.COMPATIBLE)
            
        except Exception as e:
            logger.warning(f"Error in license compatibility check: {e}")
            return False