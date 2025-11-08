from typing import Dict, Any, Tuple, List
import re
import time

# Safely import google.generativeai - may not be available on all systems
try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    genai = None

from config import config
from utils.logger import log_agent_action

class GeminiEvaluator:
    """Use Gemini AI for semantic evaluation of projects"""

    def __init__(self):
        self.model = None
        self.initialized = False
        
        # Safely initialize Gemini - don't fail if it's not available
        try:
            if not GENAI_AVAILABLE or genai is None:
                log_agent_action("Gemini", "⚠️ google-generativeai module not installed - AI evaluation disabled")
                self.initialized = False
            elif config.GEMINI_API_KEY:
                try:
                    genai.configure(api_key=config.GEMINI_API_KEY)
                    # Use gemini-2.5-flash - stable and faster model
                    self.model = genai.GenerativeModel('gemini-2.5-flash')
                    self.initialized = True
                    log_agent_action("Gemini", "✅ Gemini AI initialized successfully (model: gemini-2.5-flash)")
                except Exception as e:
                    log_agent_action("Gemini", f"❌ Failed to initialize Gemini: {str(e)}")
                    self.initialized = False
            else:
                log_agent_action("Gemini", "⚠️ Gemini API key not provided, semantic evaluation disabled")
                self.initialized = False
        except Exception as e:
            # Don't crash if Gemini module is not available
            log_agent_action("Gemini", f"⚠️ Gemini module error: {str(e)} - continuing without AI evaluation")
            self.initialized = False

    def _clean_text_for_ai(self, text: str) -> str:
        """Clean text for AI processing"""
        if not text:
            return ""

        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        # Limit length to avoid token limits
        return text[:2000]  # Gemini has token limits

    def evaluate_bot_project(self, title: str, description: str, project_index: int = 0, total_projects: int = 0) -> Tuple[float, str]:
        """
        Evaluate if project is about bot development using Gemini AI
        Returns: (score 0-1, reasoning)
        """
        if not self.initialized or not self.model:
            log_agent_action("Gemini", "⚠️ [AI] Gemini not available, using default score 0.5")
            return 0.5, "Gemini not available"

        try:
            # Log start of evaluation
            progress_info = f"({project_index}/{total_projects})" if total_projects > 0 else ""
            log_agent_action("Gemini", f"🤖 [AI] Starting bot project evaluation {progress_info}: {title[:50]}...")
            
            full_text = f"Название: {title}\nОписание: {description}"
            clean_text = self._clean_text_for_ai(full_text)
            
            log_agent_action("Gemini", f"📤 [AI] Sending request to Gemini API (text length: {len(clean_text)} chars)...")

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

            # Send request with timeout tracking
            start_time = time.time()
            log_agent_action("Gemini", f"⏳ [AI] Waiting for Gemini response...")
            
            try:
                response = self.model.generate_content(
                    prompt,
                    generation_config={
                        "temperature": 0.3,  # Lower temperature for more consistent results
                        "max_output_tokens": 100,  # Limit response length
                    }
                )
                
                elapsed_time = time.time() - start_time
                log_agent_action("Gemini", f"✅ [AI] Received response from Gemini ({elapsed_time:.2f}s)")
                
                result_text = response.text.strip()
                log_agent_action("Gemini", f"📥 [AI] Raw response: {result_text[:150]}...")

                # Parse response: "0.8, explanation"
                if ',' in result_text:
                    score_part, reason = result_text.split(',', 1)
                    try:
                        score = float(score_part.strip())
                        score = max(0.0, min(1.0, score))  # Clamp to 0-1
                        log_agent_action("Gemini", f"✅ [AI] Bot evaluation complete: score={score:.2f}, reason={reason.strip()[:50]}")
                        return score, reason.strip()
                    except ValueError as ve:
                        log_agent_action("Gemini", f"⚠️ [AI] Failed to parse score: {score_part} (error: {str(ve)})")
                else:
                    log_agent_action("Gemini", f"⚠️ [AI] Response format unexpected (no comma): {result_text[:100]}")

                # Fallback if parsing fails
                log_agent_action("Gemini", f"⚠️ [AI] Using fallback score 0.5 due to parsing error")
                return 0.5, f"Не удалось распарсить ответ AI: {result_text[:100]}"

            except Exception as api_error:
                elapsed_time = time.time() - start_time
                log_agent_action("Gemini", f"❌ [AI] API error after {elapsed_time:.2f}s: {str(api_error)[:100]}")
                raise

        except Exception as e:
            error_msg = str(e)[:100]
            log_agent_action("Gemini", f"❌ [AI] Error in bot evaluation: {error_msg}")
            return 0.5, f"Ошибка AI: {error_msg}"

    def evaluate_data_project(self, title: str, description: str, project_index: int = 0, total_projects: int = 0) -> Tuple[float, str]:
        """
        Evaluate if project is about data parsing/processing using Gemini AI
        Returns: (score 0-1, reasoning)
        """
        if not self.initialized or not self.model:
            log_agent_action("Gemini", "⚠️ [AI] Gemini not available, using default score 0.5")
            return 0.5, "Gemini not available"

        try:
            # Log start of evaluation
            progress_info = f"({project_index}/{total_projects})" if total_projects > 0 else ""
            log_agent_action("Gemini", f"📊 [AI] Starting data project evaluation {progress_info}: {title[:50]}...")
            
            full_text = f"Название: {title}\nОписание: {description}"
            clean_text = self._clean_text_for_ai(full_text)
            
            log_agent_action("Gemini", f"📤 [AI] Sending data evaluation request to Gemini API (text length: {len(clean_text)} chars)...")

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

            # Send request with timeout tracking
            start_time = time.time()
            log_agent_action("Gemini", f"⏳ [AI] Waiting for Gemini response (data evaluation)...")
            
            try:
                response = self.model.generate_content(
                    prompt,
                    generation_config={
                        "temperature": 0.3,
                        "max_output_tokens": 100,
                    }
                )
                
                elapsed_time = time.time() - start_time
                log_agent_action("Gemini", f"✅ [AI] Received response from Gemini ({elapsed_time:.2f}s)")
                
                result_text = response.text.strip()
                log_agent_action("Gemini", f"📥 [AI] Raw response: {result_text[:150]}...")

                # Parse response: "0.9, explanation"
                if ',' in result_text:
                    score_part, reason = result_text.split(',', 1)
                    try:
                        score = float(score_part.strip())
                        score = max(0.0, min(1.0, score))  # Clamp to 0-1
                        log_agent_action("Gemini", f"✅ [AI] Data evaluation complete: score={score:.2f}, reason={reason.strip()[:50]}")
                        return score, reason.strip()
                    except ValueError as ve:
                        log_agent_action("Gemini", f"⚠️ [AI] Failed to parse score: {score_part} (error: {str(ve)})")
                else:
                    log_agent_action("Gemini", f"⚠️ [AI] Response format unexpected (no comma): {result_text[:100]}")

                # Fallback if parsing fails
                log_agent_action("Gemini", f"⚠️ [AI] Using fallback score 0.5 due to parsing error")
                return 0.5, f"Не удалось распарсить ответ AI: {result_text[:100]}"

            except Exception as api_error:
                elapsed_time = time.time() - start_time
                log_agent_action("Gemini", f"❌ [AI] API error after {elapsed_time:.2f}s: {str(api_error)[:100]}")
                raise

        except Exception as e:
            error_msg = str(e)[:100]
            log_agent_action("Gemini", f"❌ [AI] Error in data evaluation: {error_msg}")
            return 0.5, f"Ошибка AI: {error_msg}"

    def evaluate_project_semantic(self, project: Dict[str, Any], project_index: int = 0, total_projects: int = 0) -> Tuple[float, List[str]]:
        """
        Comprehensive semantic evaluation using both bot and data criteria
        Returns: (score, reasons_list)
        """
        title = project.get('title', '')
        description = project.get('description', '')

        log_agent_action("Gemini", f"🎭 [AI] Starting semantic evaluation {f'({project_index}/{total_projects})' if total_projects > 0 else ''} for: {title[:50]}...")

        reasons = []
        total_score = 0.0

        # Evaluate as bot project
        log_agent_action("Gemini", f"🤖 [AI] Step 1/2: Evaluating as bot project...")
        bot_score, bot_reason = self.evaluate_bot_project(title, description, project_index, total_projects)
        if bot_score > 0.6:  # Lower threshold to show more results
            total_score = max(total_score, bot_score * 0.8)  # Weight bot projects higher
            reasons.append(f"🤖 Бот-проект: {bot_reason} (score: {bot_score:.2f})")

        # Evaluate as data project
        log_agent_action("Gemini", f"📊 [AI] Step 2/2: Evaluating as data project...")
        data_score, data_reason = self.evaluate_data_project(title, description, project_index, total_projects)
        if data_score > 0.6:  # Lower threshold
            total_score = max(total_score, data_score * 0.7)  # Data projects weight
            reasons.append(f"📊 Проект данных: {data_reason} (score: {data_score:.2f})")

        # If both are relevant, boost score
        if bot_score > 0.5 and data_score > 0.5:
            total_score = min(1.0, total_score + 0.1)
            reasons.append("🎯 Комбинированный проект (боты + данные)")

        # Add final score
        reasons.insert(0, f"🎭 AI semantic score: {total_score:.2f}")

        log_agent_action("Gemini", f"✅ [AI] Semantic evaluation complete: final_score={total_score:.2f}, bot={bot_score:.2f}, data={data_score:.2f}")

        return total_score, reasons
