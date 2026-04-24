import google.generativeai as genai
from config import config
from utils.logger import log_agent_action

class CPGenerator:
    def __init__(self):
        if config.GEMINI_API_KEY:
            genai.configure(api_key=config.GEMINI_API_KEY)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        else:
            self.model = None

    async def generate_proposal(self, project_description: str, budget: str = "Не указан") -> str:
        """Generate a commercial proposal using Gemini"""
        if not self.model:
            return "Gemini API key not configured."

        try:
            prompt = config.GEMINI_CP_PROMPT.format(
                description=project_description,
                budget=budget
            )
            
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            log_agent_action("CP Generator", f"❌ Error generating CP: {e}", level="ERROR")
            return f"Error: {str(e)}"

cp_generator = CPGenerator()
