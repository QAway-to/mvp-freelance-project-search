"""
Semantic Project Evaluator using Google Gemini Embeddings
Uses text-embedding-004 model to compute semantic similarity between project descriptions
and reference examples of relevant/irrelevant projects.
"""
import os
from typing import Dict, Any, Tuple, List, Optional
import numpy as np
from utils.logger import log_agent_action

# Try to import google-generativeai, fail gracefully if not available
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None

# Reference examples for relevant projects
RELEVANT_EXAMPLES = [
    "Создание телеграм-бота для автоматизации бизнес-процессов",
    "Разработка чат-бота на Python с API-интеграцией",
    "AI-бот для обработки сообщений и ответов пользователям",
    "Интеграция Telegram Bot API и FastAPI",
    "Настройка бота с логикой и базой данных",
    "Бот для маркетплейса, заказов, анкет, заявок",
    "Парсер для сбора информации с сайтов",
    "Парсинг HTML-страниц, выгрузка данных в Excel или БД",
    "Обработка данных, очистка, фильтрация, агрегация",
    "Скрипт для автоматической выгрузки данных из API",
    "Парсер новостей, объявлений, товаров",
    "Интеграция парсера с базой PostgreSQL или Google Sheets",
    "Создание REST API",
    "Интеграция внешних сервисов, CRM, вебхуков",
    "Разработка бекэнда на FastAPI, Flask или Django",
    "Подключение сторонних API для обмена данными",
    "Построение сервиса по обработке запросов пользователей",
    "Нужно разработать Telegram-бота для подбора фильмов по жанрам с интеграцией IMDb API",
    "Создать скрипт для парсинга данных о товарах с сайта и загрузки в Google Sheets",
    "Разработать FastAPI-сервис, который обрабатывает запросы от чат-бота и отправляет ответы через Telegram API",
    "Создать Python-приложение, которое анализирует CSV-файлы, очищает и отправляет данные в CRM",
]

# Reference examples for irrelevant projects (false positives)
IRRELEVANT_EXAMPLES = [
    "Добрый день! Я турагент, сотрудничаю со всеми ведущими туроператорами. Работаю через Telegram-бота, где можно подобрать тур. Ищу людей, готовых искать клиентов.",
    "Продвижение телеграм-канала и настройка рекламных объявлений",
    "Нужен дизайнер для создания аватарки для телеграм-бота",
    "Поиск клиентов на покупку тура через телеграм бота",
    "Маркетинг и продвижение бота в социальных сетях",
    "Создание контента для телеграм-канала",
    "Написание текстов для описания бота",
]


class SemanticEvaluator:
    """Semantic evaluation using Gemini embeddings"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        self.initialized = False
        self.relevant_embeddings = []
        self.irrelevant_embeddings = []
        
        if not GEMINI_AVAILABLE:
            log_agent_action("SemanticEvaluator", "⚠️ google-generativeai not installed. Install with: pip install google-generativeai")
            return
        
        if not self.api_key:
            log_agent_action("SemanticEvaluator", "⚠️ GEMINI_API_KEY not set. Semantic evaluation will be disabled.")
            return
        
        try:
            # Configure Gemini API
            genai.configure(api_key=self.api_key)
            
            # Get embeddings for reference examples
            log_agent_action("SemanticEvaluator", "🔄 Initializing semantic evaluator with reference examples...")
            self._load_reference_embeddings()
            self.initialized = True
            log_agent_action("SemanticEvaluator", f"✅ Semantic evaluator initialized: {len(self.relevant_embeddings)} relevant, {len(self.irrelevant_embeddings)} irrelevant examples")
        except Exception as e:
            log_agent_action("SemanticEvaluator", f"❌ Failed to initialize semantic evaluator: {str(e)}")
            self.initialized = False
    
    def _get_embedding(self, text: str) -> Optional[np.ndarray]:
        """Get embedding for text using Gemini text-embedding-004 model"""
        if not self.initialized or not genai:
            return None
        
        try:
            # Use text-embedding-004 model
            result = genai.embed_content(
                model="models/text-embedding-004",
                content=text,
                task_type="retrieval_document"
            )
            embedding = result['embedding']
            return np.array(embedding)
        except Exception as e:
            log_agent_action("SemanticEvaluator", f"⚠️ Error getting embedding: {str(e)[:100]}")
            return None
    
    def _load_reference_embeddings(self):
        """Load embeddings for all reference examples"""
        # Get embeddings for relevant examples
        for example in RELEVANT_EXAMPLES:
            embedding = self._get_embedding(example)
            if embedding is not None:
                self.relevant_embeddings.append((example, embedding))
        
        # Get embeddings for irrelevant examples
        for example in IRRELEVANT_EXAMPLES:
            embedding = self._get_embedding(example)
            if embedding is not None:
                self.irrelevant_embeddings.append((example, embedding))
        
        log_agent_action("SemanticEvaluator", f"📊 Loaded {len(self.relevant_embeddings)} relevant and {len(self.irrelevant_embeddings)} irrelevant embeddings")
    
    def cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Compute cosine similarity between two vectors"""
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def evaluate_semantic_relevance(
        self, 
        title: str, 
        description: str,
        threshold: float = 0.75
    ) -> Tuple[float, str, bool, str]:
        """
        Evaluate semantic relevance of project description
        
        Args:
            title: Project title
            description: Project description
            threshold: Minimum similarity threshold (default: 0.75)
        
        Returns:
            Tuple of (max_similarity, best_match_text, is_relevant, verdict)
        """
        if not self.initialized:
            # If not initialized, return neutral score
            return 0.5, "", True, "Semantic evaluation not available"
        
        # Combine title and description
        full_text = f"{title} {description}".strip()
        
        if not full_text:
            return 0.0, "", False, "Empty text"
        
        # Get embedding for project text
        project_embedding = self._get_embedding(full_text)
        if project_embedding is None:
            return 0.5, "", True, "Failed to get embedding"
        
        # Find maximum similarity with relevant examples
        max_relevant_similarity = 0.0
        best_relevant_match = ""
        
        for example_text, example_embedding in self.relevant_embeddings:
            similarity = self.cosine_similarity(project_embedding, example_embedding)
            if similarity > max_relevant_similarity:
                max_relevant_similarity = similarity
                best_relevant_match = example_text
        
        # Find maximum similarity with irrelevant examples
        max_irrelevant_similarity = 0.0
        best_irrelevant_match = ""
        
        for example_text, example_embedding in self.irrelevant_embeddings:
            similarity = self.cosine_similarity(project_embedding, example_embedding)
            if similarity > max_irrelevant_similarity:
                max_irrelevant_similarity = similarity
                best_irrelevant_match = example_text
        
        # Determine relevance
        # If similarity to relevant examples is high AND higher than irrelevant, it's relevant
        is_relevant = max_relevant_similarity >= threshold and max_relevant_similarity > max_irrelevant_similarity
        
        if is_relevant:
            verdict = f"✅ Релевантно (similarity: {max_relevant_similarity:.2f})"
            best_match = best_relevant_match
            max_similarity = max_relevant_similarity
        else:
            if max_irrelevant_similarity > max_relevant_similarity:
                verdict = f"❌ Не релевантно (similar to irrelevant: {max_irrelevant_similarity:.2f})"
                best_match = best_irrelevant_match
                max_similarity = max_irrelevant_similarity
            else:
                verdict = f"❌ Не релевантно (similarity: {max_relevant_similarity:.2f} < {threshold})"
                best_match = best_relevant_match
                max_similarity = max_relevant_similarity
        
        return max_similarity, best_match, is_relevant, verdict

