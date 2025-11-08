import google.generativeai as genai
from typing import Dict, Any, Tuple, List
import re
from config import config
from utils.logger import log_agent_action

class GeminiEvaluator:
    """Use Gemini AI for semantic evaluation of projects"""

    def __init__(self):
        self.model = None
        if config.GEMINI_API_KEY:
            try:
                genai.configure(api_key=config.GEMINI_API_KEY)
                self.model = genai.GenerativeModel('gemini-pro')
                log_agent_action("Gemini", "✅ Gemini AI initialized successfully")
            except Exception as e:
                log_agent_action("Gemini", f"❌ Failed to initialize Gemini: {str(e)}")
        else:
            log_agent_action("Gemini", "⚠️ Gemini API key not provided, semantic evaluation disabled")

    def _clean_text_for_ai(self, text: str) -> str:
        """Clean text for AI processing"""
        if not text:
            return ""

        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        # Limit length to avoid token limits
        return text[:2000]  # Gemini has token limits

    def evaluate_bot_project(self, title: str, description: str) -> Tuple[float, str]:
        """
        Evaluate if project is about bot development using Gemini AI
        Returns: (score 0-1, reasoning)
        """
        if not self.model:
            return 0.5, "Gemini not available"

        try:
            full_text = f"Название: {title}\nОписание: {description}"
            clean_text = self._clean_text_for_ai(full_text)

            prompt = f"""
            Проанализируй этот проект и определи, насколько он подходит для разработчика Telegram/Discord/VK ботов.

            Проект:
            {clean_text}

            Оцени по шкале 0.0 до 1.0, где:
            - 1.0: Идеально подходит (создание бота, автоматизация чатов, интеграция API)
            - 0.8: Хорошо подходит (боты + смежные технологии)
            - 0.5: Возможно подходит (требует уточнения)
            - 0.2: Слабо подходит (косвенно связано)
            - 0.0: Не подходит (дизайн, тексты, другие сферы)

            Верни только число от 0.0 до 1.0 и краткое объяснение через запятую.
            Формат: "0.8, создание Telegram бота для автоматизации"
            """

            response = self.model.generate_content(prompt)
            result_text = response.text.strip()

            # Parse response: "0.8, explanation"
            if ',' in result_text:
                score_part, reason = result_text.split(',', 1)
                try:
                    score = float(score_part.strip())
                    score = max(0.0, min(1.0, score))  # Clamp to 0-1
                    return score, reason.strip()
                except ValueError:
                    pass

            # Fallback if parsing fails
            return 0.5, f"Не удалось распарсить ответ AI: {result_text[:100]}"

        except Exception as e:
            log_agent_action("Gemini", f"❌ Error in bot evaluation: {str(e)}")
            return 0.5, f"Ошибка AI: {str(e)[:50]}"

    def evaluate_data_project(self, title: str, description: str) -> Tuple[float, str]:
        """
        Evaluate if project is about data parsing/processing using Gemini AI
        Returns: (score 0-1, reasoning)
        """
        if not self.model:
            return 0.5, "Gemini not available"

        try:
            full_text = f"Название: {title}\nОписание: {description}"
            clean_text = self._clean_text_for_ai(full_text)

            prompt = f"""
            Проанализируй этот проект и определи, насколько он подходит для специалиста по парсингу и обработке данных.

            Проект:
            {clean_text}

            Оцени по шкале 0.0 до 1.0, где:
            - 1.0: Идеально подходит (парсинг сайтов, обработка данных, API интеграции, ETL)
            - 0.8: Хорошо подходит (данные + автоматизация)
            - 0.5: Возможно подходит (работа с данными)
            - 0.2: Слабо подходит (косвенно связано с данными)
            - 0.0: Не подходит (дизайн, боты, другие сферы)

            Верни только число от 0.0 до 1.0 и краткое объяснение через запятую.
            Формат: "0.9, парсинг и обработка данных из API"
            """

            response = self.model.generate_content(prompt)
            result_text = response.text.strip()

            # Parse response: "0.9, explanation"
            if ',' in result_text:
                score_part, reason = result_text.split(',', 1)
                try:
                    score = float(score_part.strip())
                    score = max(0.0, min(1.0, score))  # Clamp to 0-1
                    return score, reason.strip()
                except ValueError:
                    pass

            # Fallback if parsing fails
            return 0.5, f"Не удалось распарсить ответ AI: {result_text[:100]}"

        except Exception as e:
            log_agent_action("Gemini", f"❌ Error in data evaluation: {str(e)}")
            return 0.5, f"Ошибка AI: {str(e)[:50]}"

    def evaluate_project_semantic(self, project: Dict[str, Any]) -> Tuple[float, List[str]]:
        """
        Comprehensive semantic evaluation using both bot and data criteria
        Returns: (score, reasons_list)
        """
        title = project.get('title', '')
        description = project.get('description', '')

        reasons = []
        total_score = 0.0

        # Evaluate as bot project
        bot_score, bot_reason = self.evaluate_bot_project(title, description)
        if bot_score > 0.7:
            total_score = max(total_score, bot_score * 0.8)  # Weight bot projects higher
            reasons.append(f"🤖 Бот-проект: {bot_reason} (score: {bot_score:.2f})")

        # Evaluate as data project
        data_score, data_reason = self.evaluate_data_project(title, description)
        if data_score > 0.7:
            total_score = max(total_score, data_score * 0.7)  # Data projects weight
            reasons.append(f"📊 Проект данных: {data_reason} (score: {data_score:.2f})")

        # If both are relevant, boost score
        if bot_score > 0.6 and data_score > 0.6:
            total_score = min(1.0, total_score + 0.1)
            reasons.append("🎯 Комбинированный проект (боты + данные)")

        # Add final score
        reasons.insert(0, f"🎭 AI semantic score: {total_score:.2f}")

        return total_score, reasons
