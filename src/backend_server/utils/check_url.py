# These URLs may be of the following three categories:
# • Model URL (e.g. https://huggingface.co/google/gemma-3-270m/tree/main)
# • Dataset URL: (e.g. https://huggingface.co/datasets/xlangai/AgentNet)
# • Code URL: ( e.g. https://github.com/SkyworkAI/Matrix-Game)

from src.utils.hf_api import hfAPI

def checkURL(url):
    if "github" in url or "datasets" in url:
        return False
    else:
        api = hfAPI()
        api.get_info(url, False)
        return True
