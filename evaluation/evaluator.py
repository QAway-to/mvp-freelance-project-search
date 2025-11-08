from typing import Dict, Any, Tuple, List
import re
from config import config
from utils.logger import log_agent_action
from evaluation.gemini_evaluator import GeminiEvaluator

class ProjectEvaluator:
    def __init__(self):
        # Initialize Gemini AI evaluator
        self.gemini = GeminiEvaluator()

        # Keywords for bot-related projects
        self.bot_keywords = {
            'бот', 'telegram', 'discord', 'vkontakte', 'vk', 'telegram bot', 'discord bot',
            'чатбот', 'бот для', 'автоматизация', 'автобот', 'парсер', 'скрипт',
            'api', 'webhook', 'интеграция', 'автоматизировать'
        }

        # Keywords for data processing projects
        self.data_keywords = {
            'парсер', 'парсинг', 'данные', 'data', 'обработка данных', 'анализ данных',
            'api', 'интеграция', 'автоматизация', 'скрипт', 'web scraping', 'сбор данных',
            'etl', 'база данных', 'database', 'sql', 'mongodb', 'postgresql'
        }

        # Programming languages/frameworks (expanded)
        self.tech_keywords = {
            'python', 'javascript', 'node.js', 'php', 'java', 'c#', 'c++',
            'telegram api', 'discord.py', 'aiogram', 'telebot', 'vk api',
            'requests', 'beautifulsoup', 'selenium', 'scrapy', 'pandas', 'numpy'
        }

        # Negative keywords (exclude these)
        self.negative_keywords = {
            'дизайн', 'логотип', 'баннер', 'фото', 'видео', 'монтаж', 'анимация',
            'текст', 'копирайтинг', 'перевод', 'статья', 'презентация',
            'верстка', 'html', 'css', 'фронтенд', 'ui/ux', 'графика'
        }

    def clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        if not text:
            return ""

        # Convert to lowercase
        text = text.lower()

        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)

        # Remove punctuation except spaces
        text = re.sub(r'[^\w\s]', '', text)

        return text.strip()

    def calculate_keyword_score(self, text: str, keywords: set, weight: float = 1.0) -> float:
        """Calculate score based on keyword matches (substring matching for flexibility)"""
        if not text:
            return 0.0

        cleaned_text = self.clean_text(text)
        words = set(cleaned_text.split())
        
        # Also check for substring matches (more flexible)
        text_lower = cleaned_text.lower()
        
        # Count exact word matches
        exact_matches = len(words.intersection(keywords))
        
        # Count substring matches (e.g., "telegram" matches "telegrambot")
        substring_matches = 0
        for keyword in keywords:
            if keyword.lower() in text_lower:
                substring_matches += 1
        
        # Use the higher of the two match counts
        matches = max(exact_matches, substring_matches)

        # More lenient scoring - since we're already searching by "бот"
        # projects are likely to be relevant
        if matches >= 2:
            score = weight  # Full score for 2+ matches
        elif matches == 1:
            score = weight * 0.8  # High score for single match (we're searching by "бот"!)
        else:
            # Even with 0 explicit matches, if we're searching by "бот", 
            # give some baseline score (projects may contain related terms)
            score = weight * 0.3  # Baseline relevance

        return score

    def has_negative_keywords(self, text: str) -> bool:
        """Check if text contains negative keywords"""
        if not text:
            return False

        cleaned_text = self.clean_text(text)
        words = set(cleaned_text.split())

        return len(words.intersection(self.negative_keywords)) > 0

    def evaluate_budget(self, budget_text: str) -> float:
        """Evaluate budget suitability (prefer reasonable budgets)"""
        if not budget_text:
            return 0.5  # Neutral score

        # Extract numbers from budget
        numbers = re.findall(r'\d+', budget_text.replace(' ', ''))

        if not numbers:
            return 0.5

        try:
            budget = int(numbers[0])

            # Prefer budgets between 1000-30000 rubles
            if 1000 <= budget <= 30000:
                return 1.0
            elif budget < 1000:
                return 0.7  # Too low, but possible
            else:
                return 0.8  # High budget, still good

        except:
            return 0.5

    def evaluate_project(self, project: Dict[str, Any], project_index: int = 0, total_projects: int = 0) -> Tuple[float, List[str]]:
        """
        Evaluate project relevance using rule-based + AI semantic analysis
        Returns: (score, reasons)
        """
        reasons = []
        score = 0.0

        title = project.get('title', '')
        description = project.get('description', '')
        budget = project.get('budget', '')

        # Combine title and description for analysis
        full_text = f"{title} {description}"

        # Check for negative keywords first - hard filter
        if self.has_negative_keywords(full_text):
            log_agent_action("Evaluator", f"🚫 [RULE] Project {project_index}/{total_projects} rejected: negative keywords")
            return 0.0, ["❌ Contains negative keywords (design, text, etc.)"]

        log_agent_action("Evaluator", f"📊 [RULE] Starting rule-based evaluation {project_index}/{total_projects}...")

        # RULE-BASED EVALUATION (keyword matching)
        rule_score = 0.0

        # Bot-related keywords (weight: 0.4)
        bot_score = self.calculate_keyword_score(full_text, self.bot_keywords, 0.4)
        rule_score += bot_score
        if bot_score > 0.1:
            reasons.append(f"🔍 Bot keywords: {bot_score:.2f}")

        # Data processing keywords (weight: 0.4)
        data_score = self.calculate_keyword_score(full_text, self.data_keywords, 0.4)
        rule_score += data_score
        if data_score > 0.1:
            reasons.append(f"📊 Data keywords: {data_score:.2f}")

        # Technical keywords (weight: 0.2)
        tech_score = self.calculate_keyword_score(full_text, self.tech_keywords, 0.2)
        rule_score += tech_score
        if tech_score > 0.1:
            reasons.append(f"⚙️ Tech keywords: {tech_score:.2f}")

        # Budget evaluation (weight: 0.1)
        budget_score = self.evaluate_budget(budget) * 0.1
        rule_score += budget_score
        if budget_score > 0.05:
            reasons.append(f"💰 Budget: {budget_score:.2f}")

        # Length bonus - prefer detailed descriptions
        text_length = len(full_text)
        if text_length > 200:
            rule_score += 0.1
            reasons.append("📝 Detailed description (+0.1)")
        elif text_length > 100:
            rule_score += 0.05
            reasons.append("📝 Good description (+0.05)")

        # Bonus for search keyword match
        search_keyword = config.SEARCH_KEYWORD.lower()
        if search_keyword in full_text.lower():
            rule_score += 0.15
            reasons.append(f"🎯 Contains '{search_keyword}' (+0.15)")

        log_agent_action("Evaluator", f"✅ [RULE] Rule-based evaluation complete: score={rule_score:.2f}")

        # AI SEMANTIC EVALUATION (Gemini) - with progress info
        ai_score = 0.0
        log_agent_action("Evaluator", f"🤖 [AI] Starting AI semantic evaluation {project_index}/{total_projects}...")
        try:
            ai_score, ai_reasons = self.gemini.evaluate_project_semantic(project, project_index, total_projects)
            if ai_score > 0.1:
                reasons.extend(ai_reasons)
            else:
                reasons.append("🤖 AI evaluation: neutral/low relevance")
            log_agent_action("Evaluator", f"✅ [AI] AI evaluation complete: score={ai_score:.2f}")
        except Exception as e:
            log_agent_action("Evaluator", f"⚠️ [AI] AI evaluation failed: {str(e)[:100]}")
            reasons.append("🤖 AI evaluation: failed")

        # COMBINE SCORES: Rule-based (60%) + AI (40%)
        # This gives more weight to rule-based for speed, but AI for accuracy
        final_score = (rule_score * 0.6) + (ai_score * 0.4)

        # Boost if both rule-based and AI agree
        if rule_score > 0.3 and ai_score > 0.3:
            final_score = min(1.0, final_score + 0.1)
            reasons.append("✅ Rule-based + AI consensus (+0.1)")

        # Ensure score is between 0 and 1
        final_score = max(0.0, min(1.0, final_score))

        # Add summary scores
        reasons.insert(0, f"🎯 Final score: {final_score:.2f} (Rule: {rule_score:.2f} + AI: {ai_score:.2f})")

        log_agent_action("Evaluator", f"✅ [EVALUATION] Project {project_index}/{total_projects} evaluation complete: final_score={final_score:.2f}")

        return final_score, reasons
