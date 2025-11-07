from typing import Dict, Any, Tuple, List
import re
from config import config
from utils.logger import log_agent_action

class ProjectEvaluator:
    def __init__(self):
        # Keywords for bot-related projects
        self.bot_keywords = {
            'бот', 'telegram', 'discord', 'vkontakte', 'vk', 'telegram bot', 'discord bot',
            'чатбот', 'бот для', 'автоматизация', 'автобот', 'парсер', 'скрипт',
            'api', 'webhook', 'интеграция', 'автоматизировать'
        }

        # Programming languages/frameworks
        self.tech_keywords = {
            'python', 'javascript', 'node.js', 'php', 'java', 'c#', 'c++',
            'telegram api', 'discord.py', 'aiogram', 'telebot', 'vk api'
        }

        # Negative keywords (exclude these)
        self.negative_keywords = {
            'дизайн', 'логотип', 'баннер', 'фото', 'видео', 'монтаж', 'анимация',
            'текст', 'копирайтинг', 'перевод', 'статья', 'презентация'
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
        """Calculate score based on keyword matches"""
        if not text:
            return 0.0

        cleaned_text = self.clean_text(text)
        words = set(cleaned_text.split())

        matches = len(words.intersection(keywords))
        total_keywords = len(keywords)

        if total_keywords == 0:
            return 0.0

        return (matches / total_keywords) * weight

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

    def evaluate_project(self, project: Dict[str, Any]) -> Tuple[float, List[str]]:
        """
        Evaluate project relevance
        Returns: (score, reasons)
        """
        reasons = []
        score = 0.0

        title = project.get('title', '')
        description = project.get('description', '')
        budget = project.get('budget', '')

        # Combine title and description for analysis
        full_text = f"{title} {description}"

        # Check for negative keywords first
        if self.has_negative_keywords(full_text):
            return 0.0, ["Contains negative keywords (design, text, etc.)"]

        # Bot-related keywords (weight: 0.5)
        bot_score = self.calculate_keyword_score(full_text, self.bot_keywords, 0.5)
        score += bot_score

        if bot_score > 0:
            reasons.append(f"Bot-related keywords found ({bot_score:.2f})")

        # Technical keywords (weight: 0.3)
        tech_score = self.calculate_keyword_score(full_text, self.tech_keywords, 0.3)
        score += tech_score

        if tech_score > 0:
            reasons.append(f"Technical keywords found ({tech_score:.2f})")

        # Budget evaluation (weight: 0.2)
        budget_score = self.evaluate_budget(budget) * 0.2
        score += budget_score

        if budget_score > 0:
            reasons.append(f"Reasonable budget ({budget_score:.2f})")

        # Length check - prefer detailed descriptions
        text_length = len(full_text)
        if text_length > 100:
            score += 0.1
            reasons.append("Detailed description")
        elif text_length < 50:
            score -= 0.1
            reasons.append("Too short description")

        # Ensure score is between 0 and 1
        score = max(0.0, min(1.0, score))

        # Add final score to reasons
        reasons.insert(0, f"Final score: {score:.2f}")

        return score, reasons
