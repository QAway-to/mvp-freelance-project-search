from typing import Dict, Any, Tuple, List
import re
from config import config
from utils.logger import log_agent_action

# Try to import semantic evaluator
try:
    from evaluation.semantic_evaluator import SemanticEvaluator
    SEMANTIC_AVAILABLE = True
except (ImportError, Exception) as e:
    SEMANTIC_AVAILABLE = False
    SemanticEvaluator = None
    log_agent_action("Evaluator", f"⚠️ Semantic evaluator not available: {str(e)}")

class ProjectEvaluator:
    def __init__(self):
        # Initialize semantic evaluator if available
        self.semantic_evaluator = None
        if SEMANTIC_AVAILABLE and SemanticEvaluator and config.GEMINI_API_KEY:
            try:
                self.semantic_evaluator = SemanticEvaluator(api_key=config.GEMINI_API_KEY)
                if not self.semantic_evaluator.initialized:
                    log_agent_action("Evaluator", "⚠️ Semantic evaluator not initialized - using rule-based evaluation only")
                    self.semantic_evaluator = None
            except Exception as e:
                log_agent_action("Evaluator", f"⚠️ Failed to initialize semantic evaluator: {str(e)}")
                self.semantic_evaluator = None
        else:
            if not config.GEMINI_API_KEY:
                log_agent_action("Evaluator", "⚠️ GEMINI_API_KEY not set - semantic evaluation disabled")
            else:
                log_agent_action("Evaluator", "⚠️ Semantic evaluator not available - using rule-based evaluation only")
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

    def evaluate_project(self, project: Dict[str, Any]) -> Tuple[float, List[str]]:
        """
        Evaluate project relevance using rule-based + semantic analysis
        Returns: (score, reasons)
        """
        reasons = []
        score = 0.0

        title = project.get('title', '')
        description = project.get('description', '')
        budget = project.get('budget', '')

        # Combine title and description for analysis
        full_text = f"{title} {description}"

        # SEMANTIC EVALUATION (first check - most accurate)
        semantic_relevant = True
        semantic_similarity = 0.0
        semantic_verdict = ""
        
        if self.semantic_evaluator and self.semantic_evaluator.initialized:
            try:
                log_agent_action("Evaluator", f"🤖 [SEMANTIC] Starting semantic evaluation for: {title[:50]}...")
                semantic_similarity, best_match, semantic_relevant, semantic_verdict = self.semantic_evaluator.evaluate_semantic_relevance(
                    title=title,
                    description=description,
                    threshold=config.SEMANTIC_SIMILARITY_THRESHOLD
                )
                
                if not semantic_relevant:
                    # If semantic evaluation says it's not relevant, reject immediately
                    log_agent_action("Evaluator", f"❌ [SEMANTIC] Project rejected by semantic evaluation: {semantic_verdict}")
                    reasons.append(f"🤖 Semantic: {semantic_verdict}")
                    reasons.append(f"📊 Similarity: {semantic_similarity:.2f}")
                    if best_match:
                        reasons.append(f"🔍 Best match: {best_match[:60]}...")
                    return 0.0, reasons
                else:
                    log_agent_action("Evaluator", f"✅ [SEMANTIC] Project passed semantic evaluation: {semantic_verdict}")
                    reasons.append(f"🤖 Semantic: ✅ Релевантно (similarity: {semantic_similarity:.2f})")
                    if best_match:
                        reasons.append(f"🔍 Best match: {best_match[:60]}...")
                    # Use semantic similarity as base score (weight: 0.6)
                    # Semantic evaluation is the primary filter
                    score = semantic_similarity * 0.6
            except Exception as e:
                log_agent_action("Evaluator", f"⚠️ [SEMANTIC] Semantic evaluation failed: {str(e)[:100]}")
                # Continue with rule-based evaluation if semantic fails

        # Check for negative keywords (fallback if semantic not available)
        if not self.semantic_evaluator or not self.semantic_evaluator.initialized:
            if self.has_negative_keywords(full_text):
                return 0.0, ["Contains negative keywords (design, text, etc.)"]
        
        # Rule-based evaluation (adds bonus points if semantic passed, or is primary if semantic not available)

        # Rule-based evaluation adds bonus points (up to 0.4 if semantic passed, or full score if semantic not available)
        rule_based_max = 0.4 if (self.semantic_evaluator and self.semantic_evaluator.initialized) else 1.0
        
        # Bot-related keywords
        bot_score_weight = 0.2 if (self.semantic_evaluator and self.semantic_evaluator.initialized) else 0.5
        bot_score = self.calculate_keyword_score(full_text, self.bot_keywords, bot_score_weight)
        score += bot_score

        if bot_score > 0.05:
            reasons.append(f"Bot-related keywords found (score: {bot_score:.2f})")

        # Technical keywords
        tech_score_weight = 0.1 if (self.semantic_evaluator and self.semantic_evaluator.initialized) else 0.3
        tech_score = self.calculate_keyword_score(full_text, self.tech_keywords, tech_score_weight)
        score += tech_score

        if tech_score > 0.05:
            reasons.append(f"Technical keywords found (score: {tech_score:.2f})")

        # Budget evaluation
        budget_score_weight = 0.05 if (self.semantic_evaluator and self.semantic_evaluator.initialized) else 0.1
        budget_score = self.evaluate_budget(budget) * budget_score_weight
        score += budget_score

        if budget_score > 0.02:
            reasons.append(f"Reasonable budget (score: {budget_score:.2f})")

        # Length bonus - prefer detailed descriptions
        text_length = len(full_text)
        if text_length > 200:
            length_bonus = 0.05 if (self.semantic_evaluator and self.semantic_evaluator.initialized) else 0.1
            score += length_bonus
            reasons.append(f"Detailed description (+{length_bonus})")
        elif text_length > 100:
            length_bonus = 0.02 if (self.semantic_evaluator and self.semantic_evaluator.initialized) else 0.05
            score += length_bonus
            reasons.append(f"Good description (+{length_bonus})")

        # Ensure score is between 0 and 1
        score = max(0.0, min(1.0, score))

        # Add final score to reasons
        if self.semantic_evaluator and self.semantic_evaluator.initialized:
            rule_based_score = score - (semantic_similarity * 0.6)
            reasons.insert(0, f"🎯 Final score: {score:.2f} (Semantic: {semantic_similarity:.2f}×0.6 + Rule-based: {rule_based_score:.2f})")
        else:
            reasons.insert(0, f"🎯 Final score: {score:.2f} (Rule-based only, semantic disabled)")

        return score, reasons
