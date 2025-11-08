from typing import Dict, Any, Tuple, List
import re
import time
import numpy as np

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
    """Use Gemini embedding model for semantic similarity evaluation"""

    def __init__(self):
        self.initialized = False
        self.bot_reference_embedding = None
        self.data_reference_embedding = None
        self.embedding_model = "models/text-embedding-004"
        
        # Safely initialize Gemini - don't fail if it's not available
        try:
            if not GENAI_AVAILABLE or genai is None:
                log_agent_action("Gemini", "⚠️ google-generativeai module not installed - AI evaluation disabled")
                self.initialized = False
            elif config.GEMINI_API_KEY:
                try:
                    genai.configure(api_key=config.GEMINI_API_KEY)
                    self.initialized = True
                    log_agent_action("Gemini", "✅ Gemini embedding model initialized successfully (model: text-embedding-004)")
                    
                    # Pre-compute reference embeddings for bot and data projects
                    self._initialize_reference_embeddings()
                    
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

    def _initialize_reference_embeddings(self):
        """Pre-compute reference embeddings for bot and data projects"""
        try:
            log_agent_action("Gemini", "🔧 [AI] Computing reference embeddings for bot and data projects...")
            
            # Reference text for bot projects
            bot_reference_text = """
            Создание Telegram бота, Discord бота, VK бота. Автоматизация чатов, 
            обработка сообщений, интеграция с API мессенджеров. Разработка ботов 
            для уведомлений, модерации, обработки команд. Использование библиотек 
            aiogram, discord.py, python-telegram-bot.
            """
            
            # Reference text for data processing projects
            data_reference_text = """
            Парсинг сайтов, web scraping, сбор данных, обработка данных, анализ данных.
            API интеграции, ETL процессы, работа с базами данных. Обработка CSV, JSON, 
            XML файлов. Использование библиотек requests, beautifulsoup, scrapy, selenium, pandas.
            """
            
            # Compute embeddings
            start_time = time.time()
            self.bot_reference_embedding = self._get_embedding(bot_reference_text)
            elapsed_bot = time.time() - start_time
            
            start_time = time.time()
            self.data_reference_embedding = self._get_embedding(data_reference_text)
            elapsed_data = time.time() - start_time
            
            log_agent_action("Gemini", f"✅ [AI] Reference embeddings computed (bot: {elapsed_bot:.2f}s, data: {elapsed_data:.2f}s)")
            
        except Exception as e:
            log_agent_action("Gemini", f"❌ [AI] Failed to compute reference embeddings: {str(e)}")
            self.initialized = False

    def _get_embedding(self, text: str) -> List[float]:
        """Get embedding vector for text using Gemini embedding model"""
        try:
            result = genai.embed_content(
                model=self.embedding_model,
                content=text,
                task_type="SEMANTIC_SIMILARITY"
            )
            return result['embedding']
        except Exception as e:
            log_agent_action("Gemini", f"❌ [AI] Error getting embedding: {str(e)}")
            raise

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        try:
            v1 = np.array(vec1)
            v2 = np.array(vec2)
            dot_product = np.dot(v1, v2)
            norm1 = np.linalg.norm(v1)
            norm2 = np.linalg.norm(v2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            similarity = dot_product / (norm1 * norm2)
            # Normalize to 0-1 range (cosine similarity is -1 to 1, but embeddings are usually positive)
            return max(0.0, min(1.0, (similarity + 1) / 2))
        except Exception as e:
            log_agent_action("Gemini", f"⚠️ [AI] Error calculating cosine similarity: {str(e)}")
            return 0.0

    def _clean_text_for_ai(self, text: str) -> str:
        """Clean text for AI processing"""
        if not text:
            return ""

        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        # Limit length to avoid token limits (embedding models have limits)
        return text[:2000]  # Gemini embedding has token limits

    def evaluate_bot_project(self, title: str, description: str, project_index: int = 0, total_projects: int = 0) -> Tuple[float, str]:
        """
        Evaluate if project is about bot development using embedding similarity
        Returns: (score 0-1, reasoning)
        """
        if not self.initialized or self.bot_reference_embedding is None:
            log_agent_action("Gemini", "⚠️ [AI] Gemini not available, using default score 0.5")
            return 0.5, "Gemini not available"

        try:
            # Log start of evaluation
            progress_info = f"({project_index}/{total_projects})" if total_projects > 0 else ""
            log_agent_action("Gemini", f"🤖 [AI] Starting bot project evaluation {progress_info}: {title[:50]}...")
            
            full_text = f"Название: {title}\nОписание: {description}"
            clean_text = self._clean_text_for_ai(full_text)
            
            log_agent_action("Gemini", f"📤 [AI] Computing embedding for project text (length: {len(clean_text)} chars)...")

            # Compute embedding for project
            start_time = time.time()
            project_embedding = self._get_embedding(clean_text)
            elapsed_time = time.time() - start_time
            log_agent_action("Gemini", f"✅ [AI] Embedding computed ({elapsed_time:.2f}s)")

            # Calculate similarity with bot reference
            similarity = self._cosine_similarity(project_embedding, self.bot_reference_embedding)
            log_agent_action("Gemini", f"📊 [AI] Bot similarity score: {similarity:.3f}")

            # Convert similarity to score (0-1 range)
            # Similarity is already normalized, but we can adjust threshold
            score = similarity
            reason = f"Семантическое сходство с бот-проектами: {similarity:.2f}"

            log_agent_action("Gemini", f"✅ [AI] Bot evaluation complete: score={score:.2f}")
            return score, reason

        except Exception as e:
            error_msg = str(e)[:100]
            log_agent_action("Gemini", f"❌ [AI] Error in bot evaluation: {error_msg}")
            return 0.5, f"Ошибка AI: {error_msg}"

    def evaluate_data_project(self, title: str, description: str, project_index: int = 0, total_projects: int = 0) -> Tuple[float, str]:
        """
        Evaluate if project is about data parsing/processing using embedding similarity
        Returns: (score 0-1, reasoning)
        """
        if not self.initialized or self.data_reference_embedding is None:
            log_agent_action("Gemini", "⚠️ [AI] Gemini not available, using default score 0.5")
            return 0.5, "Gemini not available"

        try:
            # Log start of evaluation
            progress_info = f"({project_index}/{total_projects})" if total_projects > 0 else ""
            log_agent_action("Gemini", f"📊 [AI] Starting data project evaluation {progress_info}: {title[:50]}...")
            
            full_text = f"Название: {title}\nОписание: {description}"
            clean_text = self._clean_text_for_ai(full_text)
            
            log_agent_action("Gemini", f"📤 [AI] Computing embedding for project text (length: {len(clean_text)} chars)...")

            # Compute embedding for project
            start_time = time.time()
            project_embedding = self._get_embedding(clean_text)
            elapsed_time = time.time() - start_time
            log_agent_action("Gemini", f"✅ [AI] Embedding computed ({elapsed_time:.2f}s)")

            # Calculate similarity with data reference
            similarity = self._cosine_similarity(project_embedding, self.data_reference_embedding)
            log_agent_action("Gemini", f"📊 [AI] Data similarity score: {similarity:.3f}")

            # Convert similarity to score (0-1 range)
            score = similarity
            reason = f"Семантическое сходство с проектами обработки данных: {similarity:.2f}"

            log_agent_action("Gemini", f"✅ [AI] Data evaluation complete: score={score:.2f}")
            return score, reason

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
        if bot_score > 0.5:  # Threshold for relevance
            total_score = max(total_score, bot_score * 0.8)  # Weight bot projects higher
            reasons.append(f"🤖 Бот-проект: {bot_reason} (score: {bot_score:.2f})")

        # Evaluate as data project
        log_agent_action("Gemini", f"📊 [AI] Step 2/2: Evaluating as data project...")
        data_score, data_reason = self.evaluate_data_project(title, description, project_index, total_projects)
        if data_score > 0.5:  # Threshold
            total_score = max(total_score, data_score * 0.7)  # Data projects weight
            reasons.append(f"📊 Проект данных: {data_reason} (score: {data_score:.2f})")

        # If both are relevant, boost score
        if bot_score > 0.4 and data_score > 0.4:
            total_score = min(1.0, total_score + 0.1)
            reasons.append("🎯 Комбинированный проект (боты + данные)")

        # Add final score
        reasons.insert(0, f"🎭 AI semantic score: {total_score:.2f}")

        log_agent_action("Gemini", f"✅ [AI] Semantic evaluation complete: final_score={total_score:.2f}, bot={bot_score:.2f}, data={data_score:.2f}")

        return total_score, reasons